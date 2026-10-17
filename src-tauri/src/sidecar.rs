use std::collections::VecDeque;
use std::io::{BufRead, BufReader};
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, AtomicI32, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};

use crate::ui;

pub const PORT: u16 = 8430;
const READY_TIMEOUT: Duration = Duration::from_secs(10);
const READY_POLL: Duration = Duration::from_millis(50);
const STOP_GRACE: Duration = Duration::from_secs(5);
const STDERR_LINES: usize = 40;
/// Po takhle dlouhém běhu se rozpočet restartů znovu naplní. Démon, který
/// vydržel minutu, spadl znovu „od nuly“, ne v rámci jedné poruchové série.
const UPTIME_RESET: Duration = Duration::from_secs(60);
/// Dialog běží na hlavním vlákně; když uživatel neodpoví, proces se tvrdě
/// ukončí, aby aplikace nezůstala viset navěky.
const DIALOG_TIMEOUT: Duration = Duration::from_secs(300);

pub struct SidecarHandle {
    /// `true` jen když démona spustila tahle aplikace. Cizí démon na portu
    /// 8430 se používá, ale nikdy se neukončuje.
    pub owned: Arc<AtomicBool>,
    /// PID vlastněného démona, nebo 0, když žádný neběží (mezi pády,
    /// během respawnu a po ukončení). Nikdy nesmí zůstat stale po `wait()`.
    pub pid: Arc<AtomicI32>,
    pub quitting: Arc<AtomicBool>,
}

pub fn port_open() -> bool {
    use std::net::{SocketAddr, TcpStream};
    let addr = SocketAddr::from(([127, 0, 0, 1], PORT));
    TcpStream::connect_timeout(&addr, Duration::from_millis(200)).is_ok()
}

pub fn daemon_dir_ok(dir: &Path) -> bool {
    dir.join("sysmon_app").join("__main__.py").is_file()
}

/// Rozpočet restartů: 1 s, 2 s, 4 s; čtvrtý pád už dialog.
pub fn backoff_for(attempt: usize) -> Option<Duration> {
    match attempt {
        1 => Some(Duration::from_secs(1)),
        2 => Some(Duration::from_secs(2)),
        3 => Some(Duration::from_secs(4)),
        _ => None,
    }
}

/// `rc=2` znamená chybějící build — restart by jen zopakoval tutéž chybu.
pub fn should_restart(exit_code: Option<i32>, quitting: bool) -> bool {
    !quitting && exit_code != Some(2)
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

/// Odkud se démon spustí. Rozhodnutí se dělá jednou při startu; respawn
/// po pádu musí použít stejný zdroj, ne hledat znovu.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DaemonSource {
    /// Instalovaný PyInstaller onedir vedle binárky.
    Bundled(PathBuf),
    /// Vývojový `python3 -m sysmon_app` z kořene repa.
    Source(PathBuf),
}

/// Instalovaný layout je `/usr/bin/sysmon-app` +
/// `/usr/lib/sysmon-app/daemon/sysmon-app-daemon`; stejný vztah platí
/// v AppImage mountu i v rozbaleném stromu.
pub fn bundled_daemon_path(exe: &Path) -> PathBuf {
    exe.parent()
        .unwrap_or_else(|| Path::new(""))
        .join("..")
        .join("lib")
        .join("sysmon-app")
        .join("daemon")
        .join("sysmon-app-daemon")
}

pub fn resolve_daemon(exe: &Path, cwd: &Path) -> Result<DaemonSource, String> {
    let bundled = bundled_daemon_path(exe);
    if bundled.is_file() {
        return Ok(DaemonSource::Bundled(bundled));
    }
    if daemon_dir_ok(cwd) {
        return Ok(DaemonSource::Source(cwd.to_path_buf()));
    }
    Err(format!(
        "Nenašel jsem démona.\n\
         Hledal jsem:\n  {}\n  {} (s sysmon_app/__main__.py)\n\
         Nainstaluj balíček, nebo spusť aplikaci z kořene repa sysmon-app.",
        bundled.display(),
        cwd.display()
    ))
}

/// Po `fork` se PPID dítěte musí rovnat PIDu, který ho vytvořil. Porovnávat
/// proti 1 nestačí: `systemd --user` je subreaper, takže sirotek skončí pod
/// ním, ne pod PID 1.
fn parent_still_alive(actual_ppid: libc::pid_t, expected_parent: libc::pid_t) -> bool {
    actual_ppid == expected_parent
}

pub fn ensure_daemon(app: AppHandle) -> Result<SidecarHandle, String> {
    let stderr = Arc::new(Mutex::new(VecDeque::new()));
    let pid = Arc::new(AtomicI32::new(0));
    let owned = Arc::new(AtomicBool::new(false));
    let quitting = Arc::new(AtomicBool::new(false));

    if port_open() {
        return Ok(SidecarHandle {
            owned,
            pid,
            quitting,
        });
    }

    let cwd = std::env::current_dir()
        .map_err(|e| format!("Aktuální adresář nejde zjistit: {e}"))?;
    let exe = std::env::current_exe()
        .map_err(|e| format!("Cestu ke spustitelnému souboru nejde zjistit: {e}"))?;
    let source = resolve_daemon(&exe, &cwd)?;

    let mut child = spawn_daemon(&source, &stderr)?;

    if let Err(err) = wait_ready(&mut child, &stderr) {
        // Ukončit vlastní nedoběhlé dítě, ať po nás nezůstane viset.
        let _ = child.kill();
        let _ = child.wait();
        if port_open() {
            // Někdo jiný mezitím obsadil port — použij jeho démona, ale
            // nevlastni ho.
            return Ok(SidecarHandle {
                owned,
                pid,
                quitting,
            });
        }
        return Err(err);
    }

    pid.store(child.id() as i32, Ordering::SeqCst);
    owned.store(true, Ordering::SeqCst);
    let handle = SidecarHandle {
        owned: owned.clone(),
        pid: pid.clone(),
        quitting: quitting.clone(),
    };
    start_supervisor(app, Arc::new(source), child, owned, pid, quitting, stderr);
    Ok(handle)
}

fn start_supervisor(
    app: AppHandle,
    source: Arc<DaemonSource>,
    child: Child,
    owned: Arc<AtomicBool>,
    pid: Arc<AtomicI32>,
    quitting: Arc<AtomicBool>,
    stderr: Arc<Mutex<VecDeque<String>>>,
) {
    thread::spawn(move || supervise(app, source, child, owned, pid, quitting, stderr));
}

fn supervise(
    app: AppHandle,
    source: Arc<DaemonSource>,
    mut child: Child,
    owned: Arc<AtomicBool>,
    pid: Arc<AtomicI32>,
    quitting: Arc<AtomicBool>,
    stderr: Arc<Mutex<VecDeque<String>>>,
) {
    let mut attempt = 0usize;
    let mut started = Instant::now();

    loop {
        let status = child.wait();
        // Dítě je mrtvé: jeho PID je od teď stale a nesmí se na něj posílat
        // signál. Nový PID se uloží až po úspěšném `wait_ready`.
        pid.store(0, Ordering::SeqCst);
        if quitting.load(Ordering::SeqCst) {
            return;
        }
        if started.elapsed() >= UPTIME_RESET {
            attempt = 0;
        }
        let code = status.ok().and_then(|s| s.code());

        if should_restart(code, false) {
            attempt += 1;
            match backoff_for(attempt) {
                Some(delay) => {
                    thread::sleep(delay);
                    if quitting.load(Ordering::SeqCst) {
                        return;
                    }
                }
                None => {
                    // Rozpočet tří restartů je vyčerpaný.
                    if !retry_or_exit(&app, &stderr) {
                        return;
                    }
                    attempt = 0;
                }
            }
        } else {
            // `rc=2` (chybějící build) se automaticky nerestartuje.
            if port_open() {
                // Port mezitím obsadil cizí démon — žádný dialog ani restart,
                // jen si přestaneme myslet, že je náš.
                owned.store(false, Ordering::SeqCst);
                return;
            }
            if !retry_or_exit(&app, &stderr) {
                return;
            }
            attempt = 0;
        }

        // Respawn: dokud se nový démon nepřipojí, zkoušíme to na pokyn
        // uživatele (nebo po backoffu výše).
        loop {
            if quitting.load(Ordering::SeqCst) {
                return;
            }
            if port_open() {
                // Port mezitím někdo obsadil — náš démon tam nemůže a ten
                // cizí nevlastníme.
                owned.store(false, Ordering::SeqCst);
                pid.store(0, Ordering::SeqCst);
                return;
            }
            let ready = match spawn_daemon(&source, &stderr) {
                Ok(mut next) => match wait_ready(&mut next, &stderr) {
                    Ok(()) => Some(next),
                    Err(err) => {
                        push_stderr(&stderr, err);
                        None
                    }
                },
                Err(err) => {
                    push_stderr(&stderr, err);
                    None
                }
            };
            let Some(mut next) = ready else {
                if port_open() {
                    // Respawn selhal a port mezitím poslouchá někdo jiný.
                    owned.store(false, Ordering::SeqCst);
                    pid.store(0, Ordering::SeqCst);
                    return;
                }
                if !retry_or_exit(&app, &stderr) {
                    return;
                }
                attempt = 0;
                continue;
            };
            if quitting.load(Ordering::SeqCst) {
                let _ = next.kill();
                let _ = next.wait();
                return;
            }
            pid.store(next.id() as i32, Ordering::SeqCst);
            started = Instant::now();
            child = next;
            break;
        }
    }
}

/// Ukáže dialog „Zkusit znovu / Ukončit“. Vrací `true` pro nový pokus;
/// `false` znamená, že uživatel zvolil „Ukončit“ (nebo se dialog nepodařilo
/// doručit), a volající aplikaci ukončí. Neodpovězený dialog ukončí proces
/// přímo v `retry_dialog`.
fn retry_or_exit(app: &AppHandle, stderr: &Arc<Mutex<VecDeque<String>>>) -> bool {
    if retry_dialog(app, stderr) {
        true
    } else {
        app.exit(1);
        false
    }
}

fn retry_dialog(app: &AppHandle, stderr: &Arc<Mutex<VecDeque<String>>>) -> bool {
    let message = format!(
        "Démon se nepodařilo udržet v chodu.\n\n{}",
        stderr_tail(stderr)
    );
    let (tx, rx) = std::sync::mpsc::channel();
    let handle = app.clone();
    let queued = app.run_on_main_thread(move || {
        let retry = ui::error_dialog(&handle, &message);
        let _ = tx.send(retry);
    });
    if queued.is_err() {
        return false;
    }
    // Neodpovězený dialog by aplikaci nechal viset navěky. `app.exit()` tady
    // nestačí: hlavní vlákno je zablokované v `dialog.run()`, takže jen
    // zařadí `RequestExit` do event loopu, který ho nikdy nezpracuje.
    match rx.recv_timeout(DIALOG_TIMEOUT) {
        Ok(retry) => retry,
        Err(_) => {
            // Vlastněné dítě v tuhle chvíli neexistuje (dialog se otevírá až
            // po jeho smrti nebo selhání spawnu); případné dítě v respawnu
            // drží PDEATHSIG a zmizí s námi.
            std::process::exit(1);
        }
    }
}

fn spawn_daemon(
    source: &DaemonSource,
    stderr: &Arc<Mutex<VecDeque<String>>>,
) -> Result<Child, String> {
    let parent_pid = std::process::id() as libc::pid_t;
    let mut cmd = match source {
        DaemonSource::Bundled(path) => {
            let mut c = Command::new(path);
            c.args(["--port", &PORT.to_string()]);
            c
        }
        DaemonSource::Source(cwd) => {
            let mut c = Command::new("python3");
            c.args(daemon_args()).current_dir(cwd);
            c
        }
    };
    cmd.stdin(Stdio::null())
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

    let mut child = cmd
        .spawn()
        .map_err(|e| format!("Démona se nepodařilo spustit: {e}"))?;
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
        // Exit se kontroluje dřív než port: mrtvé dítě nemůže být připravené,
        // i kdyby port mezitím poslouchal někdo cizí.
        if let Some(status) = child.try_wait().map_err(|e| e.to_string())? {
            return Err(format!(
                "Démon skončil (kód {}).\n{}",
                status.code().unwrap_or(-1),
                stderr_tail(stderr)
            ));
        }
        if port_open() {
            return Ok(());
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
    if !handle.owned.load(Ordering::SeqCst) {
        return;
    }
    handle.quitting.store(true, Ordering::SeqCst);
    let pid = handle.pid.load(Ordering::SeqCst);
    if pid <= 0 {
        handle.pid.store(0, Ordering::SeqCst);
        return;
    }
    unsafe {
        libc::kill(pid, libc::SIGTERM);
    }
    let deadline = Instant::now() + STOP_GRACE;
    let mut alive = true;
    while Instant::now() < deadline {
        if unsafe { libc::kill(pid, 0) } != 0 {
            alive = false;
            break;
        }
        thread::sleep(Duration::from_millis(50));
    }
    // SIGKILL jen když proces do grace doby skutečně nezmizel; na už
    // zmizelý (a případně recyklovaný) PID se nesahá.
    if alive {
        unsafe {
            libc::kill(pid, libc::SIGKILL);
        }
    }
    handle.pid.store(0, Ordering::SeqCst);
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("čas po epoše")
            .as_nanos();
        let dir =
            std::env::temp_dir().join(format!("sysmon-app-{name}-{}-{nanos}", std::process::id()));
        std::fs::create_dir_all(&dir).expect("dočasný adresář");
        dir
    }

    #[test]
    fn bundled_path_is_relative_to_exe() {
        assert_eq!(
            bundled_daemon_path(Path::new("/usr/bin/sysmon-app")),
            PathBuf::from("/usr/bin/../lib/sysmon-app/daemon/sysmon-app-daemon")
        );
    }

    #[test]
    fn bundled_daemon_wins_over_source() {
        let root = temp_dir("bundled");
        let exe = root.join("usr/bin/sysmon-app");
        let daemon = root.join("usr/lib/sysmon-app/daemon/sysmon-app-daemon");
        std::fs::create_dir_all(exe.parent().unwrap()).unwrap();
        std::fs::create_dir_all(daemon.parent().unwrap()).unwrap();
        std::fs::write(&exe, b"").unwrap();
        std::fs::write(&daemon, b"").unwrap();
        let cwd = root.join("repo");
        std::fs::create_dir_all(cwd.join("sysmon_app")).unwrap();
        std::fs::write(cwd.join("sysmon_app/__main__.py"), b"").unwrap();

        // `Path` nezkracuje `..`, takže vrácená cesta má tvar podle binárky.
        assert_eq!(
            resolve_daemon(&exe, &cwd).unwrap(),
            DaemonSource::Bundled(root.join("usr/bin/../lib/sysmon-app/daemon/sysmon-app-daemon"))
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn source_is_used_when_no_bundle() {
        let root = temp_dir("source");
        let cwd = root.join("repo");
        std::fs::create_dir_all(cwd.join("sysmon_app")).unwrap();
        std::fs::write(cwd.join("sysmon_app/__main__.py"), b"").unwrap();
        let exe = root.join("usr/bin/sysmon-app");
        assert_eq!(
            resolve_daemon(&exe, &cwd).unwrap(),
            DaemonSource::Source(cwd)
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn missing_daemon_names_both_paths() {
        let root = temp_dir("missing");
        let exe = root.join("usr/bin/sysmon-app");
        let err = resolve_daemon(&exe, &root).unwrap_err();
        assert!(err.contains("sysmon-app-daemon"));
        assert!(err.contains("__main__.py"));
        let _ = std::fs::remove_dir_all(&root);
    }

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

    #[test]
    fn backoff_is_one_two_four_then_none() {
        assert_eq!(backoff_for(1), Some(Duration::from_secs(1)));
        assert_eq!(backoff_for(2), Some(Duration::from_secs(2)));
        assert_eq!(backoff_for(3), Some(Duration::from_secs(4)));
        assert_eq!(backoff_for(4), None);
    }

    #[test]
    fn rc_two_is_not_restarted() {
        assert!(!should_restart(Some(2), false));
        assert!(should_restart(Some(1), false));
        assert!(should_restart(Some(0), false));
        assert!(!should_restart(Some(1), true));
    }
}
