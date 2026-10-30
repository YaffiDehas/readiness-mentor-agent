// Desktop shell: starts the packaged FastAPI sidecar (agent-server) on a free local port, waits until it answers, then opens a window on it.
// The UI talks to the sidecar over http://127.0.0.1:<port> only; closing the app stops the sidecar.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::net::{SocketAddr, TcpListener, TcpStream};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_shell::{process::CommandChild, ShellExt};

struct Sidecar(Mutex<Option<CommandChild>>);

fn free_port() -> u16 {
    TcpListener::bind("127.0.0.1:0")
        .and_then(|l| l.local_addr())
        .map(|a| a.port())
        .unwrap_or(8787)
}

fn wait_for(port: u16, secs: u64) -> bool {
    let addr: SocketAddr = ([127, 0, 0, 1], port).into();
    let end = Instant::now() + Duration::from_secs(secs);
    while Instant::now() < end {
        if TcpStream::connect_timeout(&addr, Duration::from_millis(300)).is_ok() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(250));
    }
    false
}

fn main() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            let port = free_port();
            let (mut rx, child) = app
                .shell()
                .sidecar("agent-server")?
                .args(["--port", &port.to_string()])
                .spawn()?;
            // keep reading the sidecar's output so its pipe never fills up
            tauri::async_runtime::spawn(async move { while rx.recv().await.is_some() {} });
            app.manage(Sidecar(Mutex::new(Some(child))));
            if !wait_for(port, 90) {
                return Err("the agent server did not start in time".into());
            }
            let url = format!("http://127.0.0.1:{port}").parse()?;
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("Readiness Mentor")
                .inner_size(1200.0, 820.0)
                .build()?;
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build the Readiness Mentor app");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(state) = handle.try_state::<Sidecar>() {
                if let Some(child) = state.0.lock().unwrap().take() {
                    let _ = child.kill();
                }
            }
        }
    });
}
