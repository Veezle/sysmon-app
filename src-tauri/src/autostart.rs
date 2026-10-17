use std::ffi::OsStr;
use std::fs;
use std::path::{Path, PathBuf};

use tauri::AppHandle;

use crate::ui;

pub fn config_dir_from(xdg: Option<&OsStr>, home: Option<&OsStr>) -> PathBuf {
    if let Some(xdg) = xdg {
        let candidate = PathBuf::from(xdg);
        if candidate.is_absolute() {
            return candidate;
        }
    }
    let home = home.map(PathBuf::from).unwrap_or_default();
    home.join(".config")
}

pub fn config_dir() -> PathBuf {
    let xdg = std::env::var_os("XDG_CONFIG_HOME");
    let home = std::env::var_os("HOME");
    config_dir_from(xdg.as_deref(), home.as_deref())
}

pub fn marker_path() -> PathBuf {
    config_dir().join("sysmon-app").join("autostart-asked")
}

pub fn desktop_path() -> PathBuf {
    config_dir().join("autostart").join("sysmon-app.desktop")
}

pub fn should_offer(desktop_exists: bool, marker_exists: bool) -> bool {
    !desktop_exists && !marker_exists
}

pub fn quote_exec(path: &Path) -> String {
    let raw = path.to_string_lossy();
    let reserved = |c: char| {
        c.is_whitespace() || "\"'\\><~|&;$*?#()`".contains(c)
    };
    if !raw.chars().any(reserved) {
        return raw.into_owned();
    }
    let escaped = raw
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('`', "\\`")
        .replace('$', "\\$");
    format!("\"{escaped}\"")
}

pub fn desktop_entry(exe: &Path) -> String {
    format!(
        "[Desktop Entry]\n\
         Type=Application\n\
         Name=Sysmon\n\
         Comment=Dashboard systémových metrik\n\
         Exec={} --hidden\n\
         Terminal=false\n\
         X-GNOME-Autostart-enabled=true\n",
        quote_exec(exe)
    )
}

pub fn hidden_from_args<I: Iterator<Item = String>>(args: I) -> bool {
    args.into_iter().any(|arg| arg == "--hidden")
}

pub fn maybe_offer(app: &AppHandle) {
    let desktop = desktop_path();
    let marker = marker_path();

    if !should_offer(desktop.exists(), marker.exists()) {
        if desktop.exists() && !marker.exists() {
            write_marker(&marker);
        }
        return;
    }

    if ui::ask_autostart(app) {
        if let Ok(exe) = std::env::current_exe() {
            if let Some(parent) = desktop.parent() {
                let _ = fs::create_dir_all(parent);
            }
            let _ = fs::write(&desktop, desktop_entry(&exe));
        }
    }
    write_marker(&marker);
}

fn write_marker(marker: &Path) {
    if let Some(parent) = marker.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let _ = fs::write(marker, b"");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn absolute_xdg_wins() {
        assert_eq!(
            config_dir_from(Some(OsStr::new("/tmp/xdg")), Some(OsStr::new("/home/u"))),
            PathBuf::from("/tmp/xdg")
        );
    }

    #[test]
    fn relative_xdg_is_ignored() {
        assert_eq!(
            config_dir_from(Some(OsStr::new("rel")), Some(OsStr::new("/home/u"))),
            PathBuf::from("/home/u/.config")
        );
    }

    #[test]
    fn missing_xdg_uses_home() {
        assert_eq!(
            config_dir_from(None, Some(OsStr::new("/home/u"))),
            PathBuf::from("/home/u/.config")
        );
    }

    #[test]
    fn plain_path_is_not_quoted() {
        assert_eq!(quote_exec(Path::new("/usr/bin/sysmon-app")), "/usr/bin/sysmon-app");
    }

    #[test]
    fn path_with_space_is_quoted() {
        assert_eq!(
            quote_exec(Path::new("/tmp/a b/sysmon-app")),
            "\"/tmp/a b/sysmon-app\""
        );
    }

    #[test]
    fn quotes_and_backslashes_are_escaped() {
        assert_eq!(
            quote_exec(Path::new("/tmp/a\"b\\c")),
            "\"/tmp/a\\\"b\\\\c\""
        );
    }

    #[test]
    fn desktop_entry_has_hidden_exec() {
        let entry = desktop_entry(Path::new("/usr/bin/sysmon-app"));
        assert!(entry.contains("Name=Sysmon"));
        assert!(entry.contains("Exec=/usr/bin/sysmon-app --hidden"));
        assert!(entry.contains("[Desktop Entry]"));
    }

    #[test]
    fn offer_only_when_neither_exists() {
        assert!(should_offer(false, false));
        assert!(!should_offer(true, false));
        assert!(!should_offer(false, true));
        assert!(!should_offer(true, true));
    }

    #[test]
    fn hidden_flag_is_parsed() {
        let args = vec!["sysmon-app".to_string(), "--hidden".to_string()];
        assert!(hidden_from_args(args.into_iter()));
        let args = vec!["sysmon-app".to_string()];
        assert!(!hidden_from_args(args.into_iter()));
    }
}
