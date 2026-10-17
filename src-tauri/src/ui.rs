use std::sync::atomic::{AtomicBool, Ordering};

use gtk::prelude::*;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Manager, WebviewUrl, WebviewWindowBuilder,
};

pub const WINDOW_LABEL: &str = "main";
pub const DASHBOARD_URL: &str = "http://127.0.0.1:8430/";

pub fn window_title_from(user: Option<&str>, host: Option<&str>) -> String {
    match (user, host) {
        (Some(u), Some(h)) if !u.is_empty() && !h.is_empty() => {
            format!("{u}@{h} — Sysmon")
        }
        (_, Some(h)) if !h.is_empty() => format!("{h} — Sysmon"),
        _ => "Sysmon".to_string(),
    }
}

pub fn hostname() -> Option<String> {
    let mut buf = [0u8; 256];
    let rc = unsafe {
        libc::gethostname(buf.as_mut_ptr() as *mut libc::c_char, buf.len())
    };
    if rc != 0 {
        return None;
    }
    let end = buf.iter().position(|&b| b == 0).unwrap_or(buf.len());
    String::from_utf8(buf[..end].to_vec())
        .ok()
        .filter(|s| !s.is_empty())
}

pub fn window_title() -> String {
    let user = std::env::var("USER").ok();
    window_title_from(user.as_deref(), hostname().as_deref())
}

/// Drží, jestli se tray podařilo vytvořit. Bez traye nemá okno kam se schovat,
/// takže zavření okna musí aplikaci ukončit.
pub struct TrayAvailable(pub AtomicBool);

#[derive(Debug, PartialEq, Eq)]
pub enum CloseAction {
    Hide,
    Exit,
}

pub fn close_action(tray_available: bool) -> CloseAction {
    if tray_available {
        CloseAction::Hide
    } else {
        CloseAction::Exit
    }
}

pub fn tray_available(app: &AppHandle) -> bool {
    app.try_state::<TrayAvailable>()
        .map(|state| state.0.load(Ordering::Relaxed))
        .unwrap_or(false)
}

pub fn create_tray(app: &AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "Otevřít dashboard", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "Ukončit", true, None::<&str>)?;
    let menu = Menu::with_items(app, &[&open, &quit])?;

    let mut builder = TrayIconBuilder::with_id("main")
        .menu(&menu)
        .tooltip("Sysmon")
        .on_menu_event(|app, event| match event.id.as_ref() {
            "open" => show_main_window(app),
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                show_main_window(tray.app_handle());
            }
        });

    if let Some(icon) = app.default_window_icon().cloned() {
        builder = builder.icon(icon);
    }
    builder.build(app)?;
    Ok(())
}

pub fn create_main_window(app: &AppHandle, hidden: bool) -> tauri::Result<()> {
    let url = DASHBOARD_URL.parse().expect("platná URL dashboardu");
    WebviewWindowBuilder::new(app, WINDOW_LABEL, WebviewUrl::External(url))
        .title(window_title())
        .inner_size(1180.0, 820.0)
        .min_inner_size(360.0, 560.0)
        .visible(!hidden)
        .build()?;
    Ok(())
}

pub fn show_main_window(app: &AppHandle) {
    if let Some(window) = app.get_webview_window(WINDOW_LABEL) {
        let _ = window.unminimize();
        let _ = window.show();
        let _ = window.set_focus();
    }
}

/// Chybový dialog se dvěma volbami: „Zkusit znovu“ vrací `true`,
/// „Ukončit“ (i zavření dialogu) vrací `false`.
pub fn error_dialog(app: &AppHandle, message: &str) -> bool {
    let parent = app
        .get_webview_window(WINDOW_LABEL)
        .and_then(|w| w.gtk_window().ok());
    let dialog = gtk::MessageDialog::new(
        parent.as_ref(),
        gtk::DialogFlags::empty(),
        gtk::MessageType::Error,
        gtk::ButtonsType::None,
        message,
    );
    dialog.set_title("Sysmon — chyba");
    dialog.add_button("Zkusit znovu", gtk::ResponseType::Yes);
    dialog.add_button("Ukončit", gtk::ResponseType::No);
    let response = dialog.run();
    dialog.close();
    response == gtk::ResponseType::Yes
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn title_uses_user_and_host() {
        assert_eq!(window_title_from(Some("veezle"), Some("arch")), "veezle@arch — Sysmon");
    }

    #[test]
    fn title_falls_back_to_host() {
        assert_eq!(window_title_from(None, Some("arch")), "arch — Sysmon");
    }

    #[test]
    fn title_falls_back_to_product_name() {
        assert_eq!(window_title_from(None, None), "Sysmon");
    }

    #[test]
    fn empty_strings_are_missing_values() {
        assert_eq!(window_title_from(Some(""), Some("arch")), "arch — Sysmon");
        assert_eq!(window_title_from(Some("veezle"), Some("")), "Sysmon");
    }

    #[test]
    fn user_without_host_is_not_used() {
        assert_eq!(window_title_from(Some("veezle"), None), "Sysmon");
        assert_eq!(window_title_from(Some(""), Some("")), "Sysmon");
    }

    #[test]
    fn close_hides_only_with_tray() {
        assert_eq!(close_action(true), CloseAction::Hide);
        assert_eq!(close_action(false), CloseAction::Exit);
    }
}
