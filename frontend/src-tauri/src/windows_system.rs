//! Trusted absolute paths for the fixed Windows system utilities the desktop
//! shell launches (#122). Launching a bare name such as `taskkill.exe` goes
//! through the search path, so a shadowing directory (Git for Windows' `/usr/bin`,
//! a planted binary, ...) could be run instead of the system utility. The
//! directories come from the OS (`GetSystemDirectoryW` /
//! `GetSystemWindowsDirectoryW`), never from `PATH` or environment variables,
//! and every failure is an `Err` -- there is no bare-name fallback.

use std::ffi::OsString;
use std::os::windows::ffi::OsStringExt;
use std::path::{Path, PathBuf};

use windows_sys::Win32::System::SystemInformation::{
    GetSystemDirectoryW, GetSystemWindowsDirectoryW,
};

/// The closed set of utilities the shell may launch. There is deliberately
/// no lookup by name, so nothing from the frontend or network can pick an
/// executable.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SystemUtility {
    /// `System32\taskkill.exe` -- owned backend process-tree cleanup.
    Taskkill,
    /// `System32\shutdown.exe` -- completed-job power-off.
    Shutdown,
    /// `<Windows>\explorer.exe` -- validated folder open. Not in System32.
    Explorer,
}

#[derive(Clone, Copy)]
enum TrustedDirectory {
    System,
    Windows,
}

impl SystemUtility {
    const fn file_name(self) -> &'static str {
        match self {
            Self::Taskkill => "taskkill.exe",
            Self::Shutdown => "shutdown.exe",
            Self::Explorer => "explorer.exe",
        }
    }

    const fn directory(self) -> TrustedDirectory {
        match self {
            Self::Taskkill | Self::Shutdown => TrustedDirectory::System,
            Self::Explorer => TrustedDirectory::Windows,
        }
    }

    /// Absolute path of the utility inside its OS-reported directory.
    pub fn path(self) -> Result<PathBuf, String> {
        let directory = match self.directory() {
            TrustedDirectory::System => query_directory(GetSystemDirectoryW, "GetSystemDirectoryW"),
            TrustedDirectory::Windows => {
                query_directory(GetSystemWindowsDirectoryW, "GetSystemWindowsDirectoryW")
            }
        }?;
        self.path_in(&directory)
    }

    fn path_in(self, directory: &Path) -> Result<PathBuf, String> {
        if !directory.is_absolute() {
            return Err(format!(
                "WINDOWS_UTILITY_UNRESOLVED: trusted directory is not absolute: {}",
                directory.display()
            ));
        }
        let path = directory.join(self.file_name());
        if path.is_file() {
            Ok(path)
        } else {
            Err(format!(
                "WINDOWS_UTILITY_UNRESOLVED: {} is missing",
                path.display()
            ))
        }
    }
}

type DirectoryApi = unsafe extern "system" fn(*mut u16, u32) -> u32;

fn query_directory(api: DirectoryApi, name: &str) -> Result<PathBuf, String> {
    let mut buffer = vec![0u16; 32_768];
    // SAFETY: the buffer is valid and writable for exactly the length passed.
    let len = unsafe { api(buffer.as_mut_ptr(), buffer.len() as u32) } as usize;
    if len == 0 || len >= buffer.len() {
        return Err(format!("WINDOWS_UTILITY_UNRESOLVED: {name} failed"));
    }
    Ok(PathBuf::from(OsString::from_wide(&buffer[..len])))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn system_directory() -> PathBuf {
        query_directory(GetSystemDirectoryW, "GetSystemDirectoryW").unwrap()
    }

    fn windows_directory() -> PathBuf {
        query_directory(GetSystemWindowsDirectoryW, "GetSystemWindowsDirectoryW").unwrap()
    }

    #[test]
    fn os_directories_are_absolute_and_nested() {
        let system = system_directory();
        let windows = windows_directory();
        assert!(system.is_absolute() && windows.is_absolute());
        assert_eq!(system.parent(), Some(windows.as_path()));
        assert!(system.file_name().unwrap().eq_ignore_ascii_case("System32"));
    }

    #[test]
    fn taskkill_and_shutdown_resolve_inside_system32() {
        for (utility, name) in [
            (SystemUtility::Taskkill, "taskkill.exe"),
            (SystemUtility::Shutdown, "shutdown.exe"),
        ] {
            let path = utility.path().unwrap();
            assert!(path.is_absolute(), "{path:?}");
            assert!(path.is_file(), "{path:?}");
            assert_eq!(path, system_directory().join(name));
        }
    }

    #[test]
    fn explorer_resolves_in_the_windows_directory_not_system32() {
        let path = SystemUtility::Explorer.path().unwrap();
        assert!(path.is_absolute() && path.is_file(), "{path:?}");
        assert_eq!(path, windows_directory().join("explorer.exe"));
        assert_ne!(path.parent(), Some(system_directory().as_path()));
    }

    #[test]
    fn relative_trusted_directory_is_rejected() {
        let err = SystemUtility::Taskkill
            .path_in(Path::new("System32"))
            .unwrap_err();
        assert!(err.starts_with("WINDOWS_UTILITY_UNRESOLVED"), "{err}");
    }

    #[test]
    fn missing_utility_is_an_error_not_a_fallback() {
        let empty = std::env::temp_dir().join(format!(
            "sorigul-122-empty-{}-{:?}",
            std::process::id(),
            std::thread::current().id()
        ));
        std::fs::create_dir_all(&empty).unwrap();
        for utility in [
            SystemUtility::Taskkill,
            SystemUtility::Shutdown,
            SystemUtility::Explorer,
        ] {
            let err = utility.path_in(&empty).unwrap_err();
            assert!(err.contains("is missing"), "{err}");
        }
        std::fs::remove_dir(&empty).unwrap();
    }
}
