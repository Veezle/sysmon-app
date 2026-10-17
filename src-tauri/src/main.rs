mod ui;

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            ui::create_main_window(app.handle(), false)?;
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("Tauri aplikaci se nepodařilo spustit");
}
