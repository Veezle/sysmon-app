mod sidecar;
mod ui;

use tauri::Manager;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let handle = match sidecar::ensure_daemon(app.handle().clone()) {
                Ok(handle) => handle,
                Err(err) => {
                    eprintln!("{err}");
                    app.handle().exit(1);
                    return Ok(());
                }
            };
            app.manage(handle);
            ui::create_main_window(app.handle(), false)?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("Tauri aplikaci se nepodařilo sestavit")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                sidecar::stop_owned(app);
            }
        });
}
