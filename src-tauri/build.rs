fn main() {
    #[cfg(target_os = "macos")]
    {
        cc::Build::new()
            .file("src/mac_permissions.m")
            .compile("mac_permissions");

        println!("cargo:rustc-link-lib=framework=AVFoundation");
        println!("cargo:rustc-link-lib=framework=Foundation");
    }

    tauri_build::build()
}
