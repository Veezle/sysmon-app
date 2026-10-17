use std::collections::VecDeque;
use std::io::{BufRead, BufReader};
use std::os::unix::process::CommandExt;
use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};

pub const PORT: u16 = 8430;
const READY_TIMEOUT: Duration = Duration::from_secs(10);
const READY_POLL: Duration = Duration::from_millis(50);
const STOP_GRACE: Duration = Duration::from_secs(5);
const STDERR_LINES: usize = 40;

pub struct SidecarHandle {
    pub owned: bool,
    pub child: Mutex<Option<Child>>,
    pub stderr: Arc<Mutex<VecDeque<String>>>,
}

pub fn port_open() -> bool {
    use std::net::{SocketAddr, TcpStream};
    let addr = SocketAddr::from(([127, 0, 0, 1], PORT));
    TcpStream::connect_timeout(&addr, Duration::from_millis(200)).is_ok()
}

pub fn daemon_dir_ok(dir: &Path) -> bool {
    dir.join("sysmon_app").join("__main__.py").is_file()
}

/// Argumenty démona. Port se předává explicitně: okno je napevno na
/// `127.0.0.1:8430`, takže i když má uživatel v `config.toml` jiný `port`,
/// démon musí poslouchat tam, kam se okno připojuje.
fn daemon_args() -> [String; 4] {
    [
        "-m".to_string(),
        "sysmon_app".to_string(),
        "--port".to_string(),
        PORT.to_string(),
    ]
}

/// Po `fork` se PPID dítěte musí rovnat PIDu, který ho vytvořil. Porovnávat
/// proti 1 nestačí: `systemd --user` je subreaper, takže sirotek skončí pod
/// ním, ne pod PID 1.
fn parent_still_alive(actual_ppid: libc::pid_t, expected_parent: libc::pid_t) -> bool {
    actual_ppid == expected_parent
}

pub fn ensure_daemon(app: AppHandle) -> Result<SidecarHandle, String> {
    if port_open() {
        return Ok(SidecarHandle {
            owned: false,
            child: Mutex::new(None),
            stderr: Arc::new(Mutex::new(VecDeque::new())),
        });
    }

    let cwd = std::env::current_dir()
        .map_err(|e| format!("Aktuální adresář nejde zjistit: {e}"))?;
    if !daemon_dir_ok(&cwd) {
        return Err(format!(
            "Nenašel jsem démona: v {} chybí sysmon_app/__main__.py.\n\
             Spusť aplikaci z kořene repa sysmon-app.",
            cwd.display()
        ));
    }

    let stderr = Arc::new(Mutex::new(VecDeque::new()));
    let mut child = spawn_daemon(&cwd, &stderr)
        .map_err(|e| format!("Démona se nepodařilo spustit: {e}"))?;

    if let Err(err) = wait_ready(&mut child, &stderr) {
        if port_open() {
            // Někdo jiný mezitím obsadil port — použij jeho démona.
            return Ok(SidecarHandle {
                owned: false,
                child: Mutex::new(None),
                stderr,
            });
        }
        return Err(err);
    }

    let _ = app;
    Ok(SidecarHandle {
        owned: true,
        child: Mutex::new(Some(child)),
        stderr,
    })
}

fn spawn_daemon(
    cwd: &Path,
    stderr: &Arc<Mutex<VecDeque<String>>>,
) -> std::io::Result<Child> {
    let parent_pid = std::process::id() as libc::pid_t;
    let mut cmd = Command::new("python3");
    cmd.args(daemon_args())
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());

    unsafe {
        cmd.pre_exec(move || {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            // Otec mohl zemřít dřív, než se prctl stihlo zapsat. Reparenting
            // nemusí skončit na PID 1, proto se porovnává skutečné PPID.
            if !parent_still_alive(libc::getppid(), parent_pid) {
                libc::_exit(1);
            }
            Ok(())
        });
    }

    let mut child = cmd.spawn()?;
    let pipe = child.stderr.take().expect("stderr je pipovaný");
    let buffer = stderr.clone();
    thread::spawn(move || {
        for line in BufReader::new(pipe).lines().map_while(Result::ok) {
            push_stderr(&buffer, line);
        }
    });
    Ok(child)
}

fn push_stderr(buffer: &Arc<Mutex<VecDeque<String>>>, line: String) {
    let mut buf = buffer.lock().unwrap();
    if buf.len() >= STDERR_LINES {
        buf.pop_front();
    }
    buf.push_back(line);
}

fn stderr_tail(buffer: &Arc<Mutex<VecDeque<String>>>) -> String {
    buffer.lock().unwrap().iter().cloned().collect::<Vec<_>>().join("\n")
}

fn wait_ready(
    child: &mut Child,
    stderr: &Arc<Mutex<VecDeque<String>>>,
) -> Result<(), String> {
    let deadline = Instant::now() + READY_TIMEOUT;
    while Instant::now() < deadline {
        if port_open() {
            return Ok(());
        }
        if let Some(status) = child.try_wait().map_err(|e| e.to_string())? {
            return Err(format!(
                "Démon skončil (kód {}).\n{}",
                status.code().unwrap_or(-1),
                stderr_tail(stderr)
            ));
        }
        thread::sleep(READY_POLL);
    }
    let _ = child.kill();
    let _ = child.wait();
    Err(format!(
        "Démon se do {} s nepřipojil na port {}.\n{}",
        READY_TIMEOUT.as_secs(),
        PORT,
        stderr_tail(stderr)
    ))
}

pub fn stop_owned(app: &AppHandle) {
    let Some(handle) = app.try_state::<SidecarHandle>() else {
        return;
    };
    if !handle.owned {
        return;
    }
    let mut slot = handle.child.lock().unwrap();
    let Some(mut child) = slot.take() else {
        return;
    };
    let pid = child.id() as i32;
    unsafe {
        libc::kill(pid, libc::SIGTERM);
    }
    let deadline = Instant::now() + STOP_GRACE;
    loop {
        match child.try_wait() {
            Ok(Some(_)) => return,
            Ok(None) if Instant::now() < deadline => {
                thread::sleep(Duration::from_millis(50));
            }
            _ => {
                let _ = child.kill();
                let _ = child.wait();
                return;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn daemon_dir_requires_main_module() {
        let root = std::env::temp_dir().join("sysmon-app-test-daemon-dir");

        let missing = root.join("missing");
        let _ = std::fs::remove_dir_all(&missing);
        assert!(!daemon_dir_ok(&missing), "neexistující adresář");

        let empty_pkg = root.join("empty-pkg");
        let _ = std::fs::remove_dir_all(&empty_pkg);
        std::fs::create_dir_all(empty_pkg.join("sysmon_app")).unwrap();
        assert!(!daemon_dir_ok(&empty_pkg), "sysmon_app/ bez __main__.py");

        let file_pkg = root.join("file-pkg");
        let _ = std::fs::remove_dir_all(&file_pkg);
        std::fs::create_dir_all(&file_pkg).unwrap();
        std::fs::write(file_pkg.join("sysmon_app"), "").unwrap();
        assert!(!daemon_dir_ok(&file_pkg), "sysmon_app jako soubor");

        let wrong_place = root.join("wrong-place");
        let _ = std::fs::remove_dir_all(&wrong_place);
        std::fs::create_dir_all(&wrong_place).unwrap();
        std::fs::write(wrong_place.join("__main__.py"), "").unwrap();
        assert!(!daemon_dir_ok(&wrong_place), "__main__.py v kořeni");

        let complete = root.join("complete");
        let _ = std::fs::remove_dir_all(&complete);
        std::fs::create_dir_all(complete.join("sysmon_app")).unwrap();
        std::fs::write(complete.join("sysmon_app/__main__.py"), "").unwrap();
        assert!(daemon_dir_ok(&complete), "kompletní sysmon_app/__main__.py");

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn parent_alive_accepts_the_spawning_pid() {
        assert!(parent_still_alive(12345, 12345));
    }

    #[test]
    fn subreaper_parent_is_not_the_spawning_pid() {
        assert!(!parent_still_alive(1426, 12345));
    }

    #[test]
    fn init_parent_is_not_the_spawning_pid() {
        assert!(!parent_still_alive(1, 12345));
    }

    #[test]
    fn daemon_args_force_the_window_port() {
        assert_eq!(daemon_args(), ["-m", "sysmon_app", "--port", "8430"]);
    }
}
