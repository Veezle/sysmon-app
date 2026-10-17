mod autostart;
mod sidecar;
mod ui;

use std::sync::atomic::AtomicBool;

use tauri::Manager;

fn main() {
    gtk::glib::set_prgname(Some("Sysmon"));
    let hidden = autostart::hidden_from_args(std::env::args());
    tauri::Builder::default()
        // Musí být první: druhá instance se ptá dřív, než by se stihl
        // zaregistrovat handler v `.setup()`.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            ui::show_main_window(app);
        }))
        .setup(move |app| {
            let handle = loop {
                match sidecar::ensure_daemon(app.handle().clone()) {
                    Ok(handle) => break handle,
                    Err(err) => {
                        // Start selhal (chybějící build, démon se nepřipojil).
                        // „Zkusit znovu“ zopakuje celý start, „Ukončit“ appku
                        // opravdu ukončí.
                        if !ui::error_dialog(app.handle(), &err) {
                            app.handle().exit(1);
                            return Ok(());
                        }
                    }
                }
            };
            app.manage(handle);

            let tray_ok = ui::status_notifier_available()
                && ui::create_tray(app.handle()).is_ok();
            app.manage(ui::TrayAvailable(AtomicBool::new(tray_ok)));

            if let Err(err) = ui::create_main_window(app.handle(), hidden && tray_ok) {
                sidecar::stop_owned(app.handle());
                return Err(err.into());
            }

            // Přepis se dělá i při `--hidden`, protože autostart startuje
            // právě tak.
            let installed = std::env::current_exe()
                .map(|exe| autostart::installed_exe(&exe))
                .unwrap_or(false);
            autostart::migrate_desktop(installed);

            if !hidden {
                autostart::maybe_offer(app.handle());
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                if ui::close_action(ui::tray_available(window.app_handle()))
                    == ui::CloseAction::Hide
                {
                    api.prevent_close();
                    let _ = window.hide();
                }
            }
        })
        .build(tauri::generate_context!())
        .expect("Tauri aplikaci se nepodařilo sestavit")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                sidecar::stop_owned(app);
            }
        });
}
