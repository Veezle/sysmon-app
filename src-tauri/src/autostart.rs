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

pub fn marker_path_in(config: &Path) -> PathBuf {
    config.join("sysmon-app").join("autostart-asked")
}

pub fn desktop_path_in(config: &Path) -> PathBuf {
    config.join("autostart").join("sysmon-app.desktop")
}

pub fn marker_path() -> PathBuf {
    marker_path_in(&config_dir())
}

pub fn desktop_path() -> PathBuf {
    desktop_path_in(&config_dir())
}

pub fn should_offer(desktop_exists: bool, marker_exists: bool) -> bool {
    !desktop_exists && !marker_exists
}

/// `.desktop` už existuje, jen marker chybí — doplní se bez dialogu, aby se
/// nabídka neopakovala.
pub fn marker_without_offer(desktop_exists: bool, marker_exists: bool) -> bool {
    desktop_exists && !marker_exists
}

pub fn quote_exec(path: &Path) -> String {
    let raw = path.to_string_lossy();
    let reserved = |c: char| c.is_whitespace() || "\"'\\><~|&;$*?#()`".contains(c);
    let arg_layer = if raw.chars().any(reserved) {
        let escaped = raw
            .replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('`', "\\`")
            .replace('$', "\\$");
        format!("\"{escaped}\"")
    } else {
        raw.into_owned()
    };
    // Keyfile vrstva: GLib čte `\` jako escape, takže každý backslash
    // z Exec vrstvy musí být v souboru zdvojený.
    arg_layer.replace('\\', "\\\\")
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

/// Cesta, kterou má autostart spouštět. U AppImage je `current_exe()`
/// efemérní mount; runtime dává skutečnou cestu v `APPIMAGE`.
pub fn autostart_exe_from(appimage: Option<&OsStr>, current: &Path) -> PathBuf {
    if let Some(raw) = appimage {
        let candidate = PathBuf::from(raw);
        if candidate.is_absolute() && candidate.is_file() {
            return candidate;
        }
    }
    current.to_path_buf()
}

pub fn autostart_exe() -> Option<PathBuf> {
    let current = std::env::current_exe().ok()?;
    Some(autostart_exe_from(
        std::env::var_os("APPIMAGE").as_deref(),
        &current,
    ))
}

/// Instalovaná cesta neleží pod `target/`; vývojový build ano. Efemérní
/// AppImage mount (`.mount_*`) je instalace jen zdánlivě — po ukončení
/// zmizí, takže se do autostartu zapsat nesmí.
pub fn installed_exe(path: &Path) -> bool {
    !path.components().any(|c| c.as_os_str() == "target")
        && !path.to_string_lossy().contains(".mount_")
}

pub fn installed_autostart() -> bool {
    autostart_exe().map(|p| installed_exe(&p)).unwrap_or(false)
}

fn autostart_disabled(content: &str) -> bool {
    content.lines().any(|line| {
        let line = line.trim();
        line == "Hidden=true" || line == "X-GNOME-Autostart-enabled=false"
    })
}

/// Přepsat `.desktop`, jen když jsme instalovaní a Exec míří jinam.
/// `None` znamená, že soubor neexistuje — o nabídku se stará `maybe_offer`.
pub fn should_rewrite(
    desktop: Option<&str>,
    current_exe: &Path,
    installed: bool,
) -> bool {
    if !installed {
        return false;
    }
    let Some(content) = desktop else {
        return false;
    };
    if autostart_disabled(content) {
        return false;
    }
    let expected = format!("Exec={} --hidden", quote_exec(current_exe));
    !content.lines().any(|line| line == expected)
}

/// Tiše přepíše zastaralý `.desktop` (z fáze 3 mířil na target/debug).
/// Marker se nemění: uživatel už jednou odpověděl a nabídka se neopakuje.
pub fn migrate_desktop(installed: bool) {
    if !installed {
        return;
    }
    let desktop = desktop_path();
    let Ok(content) = fs::read_to_string(&desktop) else {
        return;
    };
    let Some(exe) = autostart_exe() else {
        return;
    };
    if let Err(err) = exe_path_supported(&exe) {
        eprintln!("Autostart: {err}");
        return;
    }
    if !should_rewrite(Some(&content), &exe, installed) {
        return;
    }
    if let Err(err) = fs::write(&desktop, desktop_entry(&exe)) {
        eprintln!("Autostart: {} nelze přepsat: {err}", desktop.display());
    }
}

/// Cesty, které do `.desktop` zapsat nelze: non-UTF8, field code `%`
/// a kontrolní znaky (např. newline).
fn exe_path_supported(path: &Path) -> Result<(), String> {
    let Some(raw) = path.to_str() else {
        return Err("cesta ke spustitelnému souboru není v UTF-8".to_string());
    };
    if raw.contains('%') {
        return Err("cesta ke spustitelnému souboru obsahuje „%“ (field code)".to_string());
    }
    if raw.chars().any(char::is_control) {
        return Err("cesta ke spustitelnému souboru obsahuje kontrolní znak".to_string());
    }
    Ok(())
}

fn write_autostart(desktop: &Path) -> Result<(), String> {
    let exe = autostart_exe()
        .ok_or_else(|| "cestu ke spustitelnému souboru nelze zjistit".to_string())?;
    exe_path_supported(&exe)?;
    if let Some(parent) = desktop.parent() {
        fs::create_dir_all(parent)
            .map_err(|err| format!("adresář {} nelze vytvořit: {err}", parent.display()))?;
    }
    fs::write(desktop, desktop_entry(&exe))
        .map_err(|err| format!("soubor {} nelze zapsat: {err}", desktop.display()))?;
    Ok(())
}

pub fn maybe_offer(app: &AppHandle) {
    let desktop = desktop_path();
    let marker = marker_path();

    if marker_without_offer(desktop.exists(), marker.exists()) {
        write_marker_logged(&marker);
        return;
    }
    if !should_offer(desktop.exists(), marker.exists()) {
        return;
    }

    if ui::ask_autostart(app) {
        if let Err(err) = write_autostart(&desktop) {
            ui::notice_dialog(
                app,
                &format!(
                    "Autostart se nepodařilo zapsat: {err}\n\n\
                     Nabídka se zopakuje při příštím spuštění."
                ),
            );
            // Marker se nezapisuje, aby se nabídka příště zopakovala.
            return;
        }
    }
    write_marker_logged(&marker);
}

fn write_marker_logged(marker: &Path) {
    if let Err(err) = write_marker(marker) {
        eprintln!("Autostart: marker {} nelze zapsat: {err}", marker.display());
    }
}

fn write_marker(marker: &Path) -> std::io::Result<()> {
    if let Some(parent) = marker.parent() {
        fs::create_dir_all(parent)?;
    }
    fs::write(marker, b"")?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use std::os::unix::ffi::OsStrExt;

    use super::*;

    fn temp_dir(name: &str) -> PathBuf {
        let nanos = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .expect("čas po epoše")
            .as_nanos();
        let dir =
            std::env::temp_dir().join(format!("sysmon-app-{name}-{}-{nanos}", std::process::id()));
        fs::create_dir_all(&dir).expect("dočasný adresář");
        dir
    }

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
    fn marker_path_in_is_exact() {
        assert_eq!(
            marker_path_in(Path::new("/tmp/xdg")),
            PathBuf::from("/tmp/xdg/sysmon-app/autostart-asked")
        );
    }

    #[test]
    fn desktop_path_in_is_exact() {
        assert_eq!(
            desktop_path_in(Path::new("/tmp/xdg")),
            PathBuf::from("/tmp/xdg/autostart/sysmon-app.desktop")
        );
    }

    #[test]
    fn plain_path_is_not_quoted() {
        assert_eq!(
            quote_exec(Path::new("/usr/bin/sysmon-app")),
            "/usr/bin/sysmon-app"
        );
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
            "\"/tmp/a\\\\\"b\\\\\\\\c\""
        );
    }

    #[test]
    fn dollar_is_escaped_in_both_layers() {
        assert_eq!(quote_exec(Path::new("/tmp/a$b")), "\"/tmp/a\\\\$b\"");
    }

    #[test]
    fn backtick_is_escaped_in_both_layers() {
        assert_eq!(quote_exec(Path::new("/tmp/a`b")), "\"/tmp/a\\\\`b\"");
    }

    #[test]
    fn trailing_backslash_is_escaped_in_both_layers() {
        assert_eq!(quote_exec(Path::new("/tmp/a\\")), "\"/tmp/a\\\\\\\\\"");
    }

    #[test]
    fn desktop_entry_is_exact() {
        let entry = desktop_entry(Path::new("/usr/bin/sysmon-app"));
        assert_eq!(
            entry,
            "[Desktop Entry]\n\
             Type=Application\n\
             Name=Sysmon\n\
             Comment=Dashboard systémových metrik\n\
             Exec=/usr/bin/sysmon-app --hidden\n\
             Terminal=false\n\
             X-GNOME-Autostart-enabled=true\n"
        );
    }

    #[test]
    fn offer_only_when_neither_exists() {
        assert!(should_offer(false, false));
        assert!(!should_offer(true, false));
        assert!(!should_offer(false, true));
        assert!(!should_offer(true, true));
    }

    #[test]
    fn marker_without_offer_only_for_existing_desktop() {
        assert!(marker_without_offer(true, false));
        assert!(!marker_without_offer(true, true));
        assert!(!marker_without_offer(false, true));
        assert!(!marker_without_offer(false, false));
    }

    #[test]
    fn write_marker_creates_empty_file() {
        let dir = temp_dir("marker");
        let marker = dir.join("sysmon-app/autostart-asked");
        write_marker(&marker).expect("marker se zapíše");
        assert!(marker.is_file());
        assert_eq!(fs::read(&marker).expect("čtení markeru"), b"");
        fs::remove_dir_all(&dir).expect("úklid");
    }

    #[test]
    fn exe_path_supported_accepts_plain_path() {
        assert_eq!(exe_path_supported(Path::new("/usr/bin/sysmon-app")), Ok(()));
    }

    #[test]
    fn exe_path_supported_rejects_percent() {
        assert!(exe_path_supported(Path::new("/tmp/a%b/sysmon-app")).is_err());
    }

    #[test]
    fn exe_path_supported_rejects_control_characters() {
        assert!(exe_path_supported(Path::new("/tmp/a\nb/sysmon-app")).is_err());
    }

    #[test]
    fn exe_path_supported_rejects_non_utf8() {
        let raw = OsStr::from_bytes(b"/tmp/\xff/sysmon-app");
        assert!(exe_path_supported(Path::new(raw)).is_err());
    }

    #[test]
    fn installed_exe_rejects_target() {
        assert!(installed_exe(Path::new("/usr/bin/sysmon-app")));
        assert!(!installed_exe(Path::new(
            "/home/u/repo/src-tauri/target/debug/sysmon-app"
        )));
        assert!(!installed_exe(Path::new(
            "/home/u/repo/src-tauri/target/release/sysmon-app"
        )));
    }

    #[test]
    fn appimage_env_wins_when_absolute_and_exists() {
        let dir = temp_dir("appimage");
        let appimage = dir.join("Sysmon.AppImage");
        fs::write(&appimage, b"").expect("AppImage soubor");
        assert_eq!(
            autostart_exe_from(
                Some(appimage.as_os_str()),
                Path::new("/tmp/.mount_SysmonABC/usr/bin/sysmon-app")
            ),
            appimage
        );
        fs::remove_dir_all(&dir).expect("úklid");
    }

    #[test]
    fn relative_appimage_is_ignored() {
        assert_eq!(
            autostart_exe_from(
                Some(OsStr::new("rel/Sysmon.AppImage")),
                Path::new("/usr/bin/sysmon-app")
            ),
            PathBuf::from("/usr/bin/sysmon-app")
        );
    }

    #[test]
    fn missing_appimage_is_ignored() {
        let dir = temp_dir("appimage-missing");
        let missing = dir.join("neexistuje.AppImage");
        assert_eq!(
            autostart_exe_from(Some(missing.as_os_str()), Path::new("/usr/bin/sysmon-app")),
            PathBuf::from("/usr/bin/sysmon-app")
        );
        fs::remove_dir_all(&dir).expect("úklid");
    }

    #[test]
    fn no_appimage_uses_current_exe() {
        assert_eq!(
            autostart_exe_from(None, Path::new("/usr/bin/sysmon-app")),
            PathBuf::from("/usr/bin/sysmon-app")
        );
    }

    #[test]
    fn installed_exe_rejects_appimage_mount() {
        assert!(!installed_exe(Path::new(
            "/tmp/.mount_SysmonABC/usr/bin/sysmon-app"
        )));
    }

    #[test]
    fn hidden_true_is_not_rewritten() {
        let content = desktop_entry(Path::new("/old/sysmon-app")).replace(
            "Terminal=false",
            "Hidden=true\nTerminal=false",
        );
        assert!(!should_rewrite(
            Some(&content),
            Path::new("/usr/bin/sysmon-app"),
            true
        ));
    }

    #[test]
    fn disabled_gnome_autostart_is_not_rewritten() {
        let content = desktop_entry(Path::new("/old/sysmon-app")).replace(
            "X-GNOME-Autostart-enabled=true",
            "X-GNOME-Autostart-enabled=false",
        );
        assert!(!should_rewrite(
            Some(&content),
            Path::new("/usr/bin/sysmon-app"),
            true
        ));
    }

    #[test]
    fn no_desktop_means_no_rewrite() {
        assert!(!should_rewrite(None, Path::new("/usr/bin/sysmon-app"), true));
    }

    #[test]
    fn dev_run_never_rewrites() {
        let content = desktop_entry(Path::new("/usr/bin/sysmon-app"));
        assert!(!should_rewrite(
            Some(&content),
            Path::new("/home/u/repo/src-tauri/target/debug/sysmon-app"),
            false
        ));
    }

    #[test]
    fn same_exe_is_left_alone() {
        let exe = Path::new("/usr/bin/sysmon-app");
        assert!(!should_rewrite(Some(&desktop_entry(exe)), exe, true));
    }

    #[test]
    fn different_exe_is_rewritten() {
        let old = desktop_entry(Path::new("/home/u/repo/src-tauri/target/debug/sysmon-app"));
        assert!(should_rewrite(
            Some(&old),
            Path::new("/usr/bin/sysmon-app"),
            true
        ));
    }

    #[test]
    fn garbage_is_rewritten() {
        assert!(should_rewrite(
            Some("tohle není .desktop\n"),
            Path::new("/usr/bin/sysmon-app"),
            true
        ));
    }

    #[test]
    fn hidden_flag_is_parsed() {
        let args = vec!["sysmon-app".to_string(), "--hidden".to_string()];
        assert!(hidden_from_args(args.into_iter()));
        let args = vec!["sysmon-app".to_string()];
        assert!(!hidden_from_args(args.into_iter()));
    }
}
