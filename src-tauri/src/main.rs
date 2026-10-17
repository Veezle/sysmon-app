mod sidecar;
mod ui;

use std::sync::atomic::AtomicBool;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
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

            let tray_ok = ui::create_tray(app.handle()).is_ok();
            app.manage(ui::TrayAvailable(AtomicBool::new(tray_ok)));

            if let Err(err) = ui::create_main_window(app.handle(), false) {
                sidecar::stop_owned(app.handle());
                return Err(err.into());
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
