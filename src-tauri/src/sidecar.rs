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
    let mut cmd = Command::new("python3");
    cmd.arg("-m")
        .arg("sysmon_app")
        .current_dir(cwd)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::piped());

    unsafe {
        cmd.pre_exec(|| {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            // Otec mohl zemřít dřív, než se prctl stihlo zapsat.
            if libc::getppid() == 1 {
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
        let dir = std::env::temp_dir().join("sysmon-app-test-daemon-dir");
        let _ = std::fs::remove_dir_all(&dir);
        assert!(!daemon_dir_ok(&dir));
        std::fs::create_dir_all(dir.join("sysmon_app")).unwrap();
        std::fs::write(dir.join("sysmon_app/__main__.py"), "").unwrap();
        assert!(daemon_dir_ok(&dir));
        let _ = std::fs::remove_dir_all(&dir);
    }
}
