@echo off
setlocal DisableDelayedExpansion
rem Explorer closes its console when a batch file fails, including syntax errors
rem that bypass :failed/pause. Keep an outer CMD alive before entering bootstrap.
rem Explicit commands retain their non-interactive exit-code contract.
if not "%~1"=="" goto bootstrap_entry
"%SystemRoot%\System32\cmd.exe" /d /s /k ""%~f0" wizard"
exit /b %errorlevel%
:bootstrap_entry
set "AWC_STAGE="
set "AWC_STAGE_OWNED="
set "AWC_PUSHD="
set "AWC_SOURCE_PROMPTED="
set "AWC_SOURCE_MODE=online"
set "PYTHONDONTWRITEBYTECODE=1"
rem Reviewed bootstrap constants. Keep these synchronized with installation_catalog.json.
set "AWC_PY_FILE=cpython-3.11.18+20261026-x86_64-pc-windows-msvc-install_only.tar.gz"
set "AWC_PY_HASH=75cb501dc11c7b55c6b447c58e4910bce5b1f609f1017328b4f3a858dfaf5428"
set "AWC_EXE_HASH=b3dc0e0c33d56bacd2ea51da1a37744f19c1fd2460e3b8f87d08a47872226d99"
set "AWC_PY_URL=https://github.com/astral-sh/python-build-standalone/releases/download/20261026/%AWC_PY_FILE%"
set "AWC_ROOT=%~dp0"
set "AWC_REPOSITORY="
set "AWC_CA_FILE="
set "AWC_OFFLINE=%~dp0"
if exist "%~dp0..\install-manifest.json" set "AWC_OFFLINE=%~dp0.."
set "AWC_READONLY="
set "AWC_COMMAND=%~1"
if /i "%~1"=="--help" goto help
if /i "%~1"=="-h" goto help
if /i "%~1"=="help" goto help
if /i "%~1"=="doctor" set "AWC_READONLY=1"
:parse
if "%~1"=="" goto parsed
set "AWC_ARGUMENT=%~1"
if /i "%~1"=="--help" goto help
if /i "%~1"=="-h" goto help
if /i "%~1"=="--repository" goto repository
if /i "%~1"=="--offline-dir" goto offline
if /i "%~1"=="--ca-file" goto ca_file
if /i "%~1"=="--source-mode" goto source_mode
if /i "%AWC_ARGUMENT:~0,14%"=="--source-mode=" goto source_mode_equals
shift
goto parse
:repository
if "%~2"=="" goto usage_error
set "AWC_REPOSITORY=%~2"
shift
shift
goto parse
:offline
if "%~2"=="" goto usage_error
set "AWC_OFFLINE=%~f2"
shift
shift
goto parse
:ca_file
if "%~2"=="" goto usage_error
set "AWC_CA_FILE=%~f2"
shift
shift
goto parse
:source_mode
if "%~2"=="" goto usage_error
set "AWC_SOURCE_MODE=%~2"
shift
goto validate_source_mode
:source_mode_equals
set "AWC_SOURCE_MODE=%AWC_ARGUMENT:~14%"
:validate_source_mode
if "%AWC_SOURCE_MODE%"=="online" goto source_mode_valid
if "%AWC_SOURCE_MODE%"=="restricted" goto source_mode_valid
if "%AWC_SOURCE_MODE%"=="corporate" goto source_mode_valid
if "%AWC_SOURCE_MODE%"=="offline" goto source_mode_valid
goto source_mode_error
:source_mode_valid
shift
goto parse
:parsed
echo [bootstrap] Checking Windows and installation prerequisites...
if /i "%PROCESSOR_ARCHITECTURE%"=="AMD64" goto architecture_ok
if /i "%PROCESSOR_ARCHITEW6432%"=="AMD64" goto architecture_ok
echo [error] AW Center requires Windows x64.
exit /b 1
:architecture_ok
if not defined LOCALAPPDATA goto no_home
set "AWC_HOME=%LOCALAPPDATA%\AWCenter"
set "AWC_PYTHON=%LOCALAPPDATA%\AWCenter\runtimes\python-3.11.18\python\python.exe"
set "AWC_ARCHIVE=%LOCALAPPDATA%\AWCenter\cache\runtimes\%AWC_PY_FILE%"
set "AWC_CURL=%SystemRoot%\System32\curl.exe"
set "AWC_CERTUTIL=%SystemRoot%\System32\certutil.exe"
set "AWC_TAR=%SystemRoot%\System32\tar.exe"
pushd "%AWC_ROOT%"
if errorlevel 1 goto failed
set "AWC_PUSHD=1"
if defined AWC_READONLY goto readonly
if not exist "%AWC_PYTHON%" goto bootstrap
set "AWC_CHECK_PYTHON=%AWC_PYTHON%"
set "AWC_TRUST_RUNTIME=%AWC_HOME%\runtimes\python-3.11.18"
call :verify_runtime
if errorlevel 1 goto integrity_error
call :check_existing_home
if errorlevel 1 goto unsafe_home
if exist "%AWC_ARCHIVE%" goto verify_archive
goto bootstrap
:readonly
rem Doctor and help never bootstrap, create directories or download files.
if not exist "%AWC_PYTHON%" goto readonly_missing
if not exist "%AWC_CERTUTIL%" goto tools_missing
set "AWC_CHECK_PYTHON=%AWC_PYTHON%"
set "AWC_TRUST_RUNTIME=%AWC_HOME%\runtimes\python-3.11.18"
call :verify_runtime
if errorlevel 1 goto integrity_error
call :check_existing_home
if errorlevel 1 goto unsafe_home
goto launch
:readonly_missing
echo [missing] Managed Python 3.11 is not installed. Run AWCenter.cmd provision --profile dev.
goto failed
:bootstrap
if not "%AWC_SOURCE_MODE%"=="offline" if not exist "%AWC_CURL%" goto tools_missing
if not exist "%AWC_CERTUTIL%" goto tools_missing
if not exist "%AWC_TAR%" goto tools_missing
if not "%AWC_SOURCE_MODE%"=="offline" if defined AWC_CA_FILE if not exist "%AWC_CA_FILE%" goto ca_error
rem Stage outside the home: failed initial downloads cannot leave a half-created home.
set "AWC_STAGE=%LOCALAPPDATA%\AWCenter-bootstrap-%RANDOM%-%RANDOM%"
mkdir "%AWC_STAGE%" 2>nul
if errorlevel 1 goto failed
set "AWC_STAGE_OWNED=1"
set "AWC_SID="
for /f "tokens=2 delims=," %%S in ('"%SystemRoot%\System32\whoami.exe" /user /fo csv /nh') do set "AWC_SID=%%~S"
if not defined AWC_SID goto failed
"%SystemRoot%\System32\icacls.exe" "%AWC_STAGE%" /inheritance:r /grant:r "*%AWC_SID%:(OI)(CI)F" >nul 2>nul
if errorlevel 1 goto failed
"%SystemRoot%\System32\icacls.exe" "%AWC_STAGE%" /setowner "*%AWC_SID%" >nul 2>nul
if errorlevel 1 goto failed
if exist "%AWC_ARCHIVE%" goto cached_bootstrap
if "%AWC_SOURCE_MODE%"=="restricted" goto restricted_local
if "%AWC_SOURCE_MODE%"=="offline" goto local_repository
if "%AWC_SOURCE_MODE%"=="corporate" goto repository_fallback
set "AWC_FETCH_URL=%AWC_PY_URL%"
echo [bootstrap] Downloading the verified Python runtime...
call :download
if errorlevel 2 goto download_failed
if errorlevel 1 goto repository_fallback
goto accept_download
:repository_fallback
if not defined AWC_REPOSITORY goto offline_fallback
rem HTTPS repositories are byte mirrors; filenames and hashes are never read from them.
if /i "%AWC_REPOSITORY:~0,8%"=="https://" goto remote_repository
if /i "%AWC_REPOSITORY:~0,7%"=="http://" goto insecure_repository
:local_repository
if not defined AWC_REPOSITORY goto offline_fallback
if /i "%AWC_REPOSITORY:~0,8%"=="https://" goto offline_fallback
if /i "%AWC_REPOSITORY:~0,7%"=="http://" goto insecure_repository
set "AWC_LOCAL_FILE=%AWC_REPOSITORY%\%AWC_PY_FILE%"
if exist "%AWC_LOCAL_FILE%" goto accept_local
set "AWC_LOCAL_FILE=%AWC_REPOSITORY%\runtimes\%AWC_PY_FILE%"
if exist "%AWC_LOCAL_FILE%" goto accept_local
goto offline_fallback
:remote_repository
if "%AWC_SOURCE_MODE%"=="offline" goto offline_fallback
if not "%AWC_REPOSITORY:@=%"=="%AWC_REPOSITORY%" goto insecure_repository
if not "%AWC_REPOSITORY:?=%"=="%AWC_REPOSITORY%" goto insecure_repository
if not "%AWC_REPOSITORY:#=%"=="%AWC_REPOSITORY%" goto insecure_repository
set "AWC_FETCH_URL=%AWC_REPOSITORY%/%AWC_PY_FILE%"
call :download
if errorlevel 2 goto download_failed
if errorlevel 1 goto remote_repository_nested
goto accept_download
:remote_repository_nested
set "AWC_FETCH_URL=%AWC_REPOSITORY%/runtimes/%AWC_PY_FILE%"
call :download
if errorlevel 2 goto download_failed
if errorlevel 1 goto offline_fallback
goto accept_download
:offline_fallback
if "%AWC_SOURCE_MODE%"=="restricted" goto restricted_public
set "AWC_LOCAL_FILE=%AWC_OFFLINE%\%AWC_PY_FILE%"
if exist "%AWC_LOCAL_FILE%" goto accept_local
set "AWC_LOCAL_FILE=%AWC_OFFLINE%\runtimes\%AWC_PY_FILE%"
if exist "%AWC_LOCAL_FILE%" goto accept_local
:sources_missing
echo [error] Verified Python archive unavailable from sources permitted by %AWC_SOURCE_MODE% mode.
echo [info] Required file: %AWC_PY_FILE%
echo [info] Use --repository for a package mirror or --offline-dir for a directory containing this file.
if defined AWC_SOURCE_PROMPTED goto failed
if "%AWC_COMMAND%"=="" goto choose_bootstrap_sources
if /i "%AWC_COMMAND%"=="wizard" goto choose_bootstrap_sources
goto failed
:restricted_local
if not defined AWC_REPOSITORY goto restricted_offline
if /i "%AWC_REPOSITORY:~0,8%"=="https://" goto restricted_offline
if /i "%AWC_REPOSITORY:~0,7%"=="http://" goto insecure_repository
set "AWC_LOCAL_FILE=%AWC_REPOSITORY%\%AWC_PY_FILE%"
if exist "%AWC_LOCAL_FILE%" goto accept_local
set "AWC_LOCAL_FILE=%AWC_REPOSITORY%\runtimes\%AWC_PY_FILE%"
if exist "%AWC_LOCAL_FILE%" goto accept_local
:restricted_offline
set "AWC_LOCAL_FILE=%AWC_OFFLINE%\%AWC_PY_FILE%"
if exist "%AWC_LOCAL_FILE%" goto accept_local
set "AWC_LOCAL_FILE=%AWC_OFFLINE%\runtimes\%AWC_PY_FILE%"
if exist "%AWC_LOCAL_FILE%" goto accept_local
if defined AWC_REPOSITORY if /i "%AWC_REPOSITORY:~0,8%"=="https://" goto remote_repository
:restricted_public
set "AWC_FETCH_URL=%AWC_PY_URL%"
call :download
if errorlevel 2 goto download_failed
if errorlevel 1 goto sources_missing
goto accept_download
:choose_bootstrap_sources
rem This prompt must work before Python/the wizard can be installed.
set "AWC_SOURCE_PROMPTED=1"
set "AWC_NEW_REPOSITORY="
set "AWC_NEW_OFFLINE="
echo.
echo Python could not be downloaded. Supply an alternative source, or press Enter twice to exit.
echo Do not include passwords, tokens or surrounding quotes.
set /p "AWC_NEW_REPOSITORY=Package repository HTTPS URL or directory: "
set /p "AWC_NEW_OFFLINE=Offline directory containing the required archive: "
if not defined AWC_NEW_REPOSITORY if not defined AWC_NEW_OFFLINE goto failed
if defined AWC_NEW_REPOSITORY set "AWC_REPOSITORY=%AWC_NEW_REPOSITORY%"
if defined AWC_NEW_OFFLINE set "AWC_OFFLINE=%AWC_NEW_OFFLINE%"
goto repository_fallback
:accept_local
copy /b "%AWC_LOCAL_FILE%" "%AWC_STAGE%\python.part" >nul
if errorlevel 1 goto failed
:accept_download
set "AWC_VERIFY_FILE=%AWC_STAGE%\python.part"
set "AWC_VERIFY_HASH=%AWC_PY_HASH%"
call :verify
if errorlevel 1 goto integrity_error
goto expand_bootstrap
:cached_bootstrap
copy /b "%AWC_ARCHIVE%" "%AWC_STAGE%\python.part" >nul
if errorlevel 1 goto failed
set "AWC_VERIFY_FILE=%AWC_STAGE%\python.part"
set "AWC_VERIFY_HASH=%AWC_PY_HASH%"
call :verify
if errorlevel 1 goto integrity_error
:expand_bootstrap
mkdir "%AWC_STAGE%\expanded"
if errorlevel 1 goto failed
rem Only this fixed reviewed archive reaches native tar; the SHA-256 passed first.
"%AWC_TAR%" -xzf "%AWC_STAGE%\python.part" -C "%AWC_STAGE%\expanded"
if errorlevel 1 goto failed
set "AWC_VERIFY_FILE=%AWC_STAGE%\expanded\python\python.exe"
set "AWC_VERIFY_HASH=%AWC_EXE_HASH%"
call :verify
if errorlevel 1 goto integrity_error
set "AWC_CHECK_PYTHON=%AWC_STAGE%\expanded\python\python.exe"
set "AWC_TRUST_RUNTIME=%AWC_STAGE%\expanded"
call :verify_runtime
if errorlevel 1 goto integrity_error
rem Existing home permissions are checked, never repaired. Only a newly created
rem home receives the exact owner-only descriptor, before any cache/private writes.
"%AWC_CHECK_PYTHON%" -I -S -B -X utf8 -X frozen_modules=on "%AWC_ROOT%scripts\launcher\installation_verify_python.py" "%AWC_TRUST_RUNTIME%" "%AWC_ROOT%scripts\launcher\installation_python.sha256" "%AWC_ROOT%." initialize-home "%AWC_HOME%" >nul 2>nul
if errorlevel 1 goto unsafe_home
if not exist "%AWC_ARCHIVE%" move "%AWC_STAGE%\python.part" "%AWC_ARCHIVE%" >nul
if errorlevel 1 goto failed
if exist "%AWC_PYTHON%" goto verify_python
if not exist "%AWC_HOME%\runtimes" mkdir "%AWC_HOME%\runtimes"
if errorlevel 1 goto failed
if exist "%AWC_HOME%\runtimes\python-3.11.18" goto integrity_error
move "%AWC_STAGE%\expanded" "%AWC_HOME%\runtimes\python-3.11.18" >nul
if errorlevel 1 goto failed
goto verify_python
:verify_archive
set "AWC_VERIFY_FILE=%AWC_ARCHIVE%"
set "AWC_VERIFY_HASH=%AWC_PY_HASH%"
call :verify
if errorlevel 1 goto integrity_error
:verify_python
set "AWC_CHECK_PYTHON=%AWC_PYTHON%"
set "AWC_TRUST_RUNTIME=%AWC_HOME%\runtimes\python-3.11.18"
call :verify_runtime
if errorlevel 1 goto integrity_error
:launch
rem Carry bootstrap choices into the Python wizard's subsequent Node/npm setup.
set "AWCENTER_PACKAGE_REPOSITORY=%AWC_REPOSITORY%"
set "AWCENTER_OFFLINE_DIR=%AWC_OFFLINE%"
if defined AWC_STAGE_OWNED rd /s /q "%AWC_STAGE%" 2>nul
if "%AWC_COMMAND%"=="" goto wizard
"%AWC_PYTHON%" -I -S -B -X utf8 -X frozen_modules=on "%AWC_ROOT%scripts\launcher\installation_verify_python.py" "%AWC_TRUST_RUNTIME%" "%AWC_ROOT%scripts\launcher\installation_python.sha256" "%AWC_ROOT%." launch %*
set "AWC_RESULT=%errorlevel%"
if defined AWC_PUSHD popd
exit /b %AWC_RESULT%
:wizard
"%AWC_PYTHON%" -I -S -B -X utf8 -X frozen_modules=on "%AWC_ROOT%scripts\launcher\installation_verify_python.py" "%AWC_TRUST_RUNTIME%" "%AWC_ROOT%scripts\launcher\installation_python.sha256" "%AWC_ROOT%." launch wizard
set "AWC_RESULT=%errorlevel%"
echo.
pause
if defined AWC_PUSHD popd
exit /b %AWC_RESULT%
:verify
rem Fixed subroutine: never CALL user-supplied strings or manifest commands.
"%AWC_CERTUTIL%" -hashfile "%AWC_VERIFY_FILE%" SHA256 2>nul | "%SystemRoot%\System32\findstr.exe" /i /x /c:"%AWC_VERIFY_HASH%" >nul
exit /b %errorlevel%
:verify_runtime
rem Before starting ANY interpreter, pin every top-level native/control file and
rem both source/pyc versions of the forced UTF-8 startup encoding closure.
rem Extension modules and same-name packages outrank .py modules in FileFinder.
if exist "%AWC_TRUST_RUNTIME%\python\Lib\encodings\*.pyd" exit /b 1
if exist "%AWC_TRUST_RUNTIME%\python\Lib\encodings*.pyd" exit /b 1
if exist "%AWC_TRUST_RUNTIME%\python\Lib\encodings\aliases\" exit /b 1
if exist "%AWC_TRUST_RUNTIME%\python\Lib\encodings\utf_8\" exit /b 1
if not exist "%AWC_ROOT%scripts\launcher\installation_python_startup.sha256" exit /b 1
for /f "delims=" %%N in ('dir /b /a "%AWC_TRUST_RUNTIME%" 2^>nul') do (
    set "AWC_ROOT_ENTRY=%%N"
    call :allowed_runtime_root
    if errorlevel 1 exit /b 1
)
for /f "delims=" %%N in ('dir /b /a "%AWC_TRUST_RUNTIME%\python" 2^>nul') do (
    set "AWC_ROOT_ENTRY=%%N"
    call :allowed_python_root
    if errorlevel 1 exit /b 1
)
for /f "usebackq tokens=1,2 delims=|" %%H in ("%AWC_ROOT%scripts\launcher\installation_python_startup.sha256") do (
    set "AWC_VERIFY_HASH=%%H"
    set "AWC_VERIFY_FILE=%AWC_TRUST_RUNTIME%\%%I"
    call :verify
    if errorlevel 1 exit /b 1
)
exit /b 0
:allowed_runtime_root
if /i "%AWC_ROOT_ENTRY%"=="python" exit /b 0
if /i "%AWC_ROOT_ENTRY%"==".awcenter-tool.json" exit /b 0
exit /b 1
:allowed_python_root
if /i "%AWC_ROOT_ENTRY%"=="DLLs" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="LICENSE.txt" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="Lib" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="Scripts" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="include" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="libs" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="python.exe" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="python.pdb" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="python3.dll" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="python3.pdb" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="python311.dll" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="python311.pdb" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="pythonw.exe" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="pythonw.pdb" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="tcl" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="vcruntime140.dll" exit /b 0
if /i "%AWC_ROOT_ENTRY%"=="vcruntime140_1.dll" exit /b 0
exit /b 1

:check_existing_home
"%AWC_CHECK_PYTHON%" -I -S -B -X utf8 -X frozen_modules=on "%AWC_ROOT%scripts\launcher\installation_verify_python.py" "%AWC_TRUST_RUNTIME%" "%AWC_ROOT%scripts\launcher\installation_python.sha256" "%AWC_ROOT%." check-home "%AWC_HOME%" >nul 2>nul
exit /b %errorlevel%
:download
rem System TLS and inherited HTTPS_PROXY are honored. Never use --insecure.
if defined AWC_CA_FILE goto download_with_ca
"%AWC_CURL%" --disable --silent --show-error --fail --location --proto "=https" --proto-redir "=https" --disallow-username-in-url --max-filesize 1073741824 --connect-timeout 15 --max-time 300 --retry 2 --retry-connrefused --output "%AWC_STAGE%\python.part" --write-out "%%{http_code}" "%AWC_FETCH_URL%" >"%AWC_STAGE%\http-status" 2>nul
goto download_result
:download_with_ca
"%AWC_CURL%" --disable --cacert "%AWC_CA_FILE%" --silent --show-error --fail --location --proto "=https" --proto-redir "=https" --disallow-username-in-url --max-filesize 1073741824 --connect-timeout 15 --max-time 300 --retry 2 --retry-connrefused --output "%AWC_STAGE%\python.part" --write-out "%%{http_code}" "%AWC_FETCH_URL%" >"%AWC_STAGE%\http-status" 2>nul
:download_result
set "AWC_FETCH_STATUS=%errorlevel%"
if "%AWC_FETCH_STATUS%"=="0" exit /b 0
rem Publish only numeric transport diagnostics, never curl stderr or signed URLs.
set "AWC_HTTP_STATUS=unknown"
if exist "%AWC_STAGE%\http-status" set /p "AWC_HTTP_STATUS=" <"%AWC_STAGE%\http-status"
echo [download] curl exit code: %AWC_FETCH_STATUS%; HTTP status: %AWC_HTTP_STATUS%
if "%AWC_FETCH_STATUS%"=="5" echo [download] Proxy name could not be resolved. Check HTTPS_PROXY.
if "%AWC_FETCH_STATUS%"=="6" echo [download] Download host could not be resolved. Check DNS or use a package mirror.
if "%AWC_FETCH_STATUS%"=="7" echo [download] Connection failed. Check network, firewall and proxy access.
if "%AWC_FETCH_STATUS%"=="28" echo [download] Download timed out. Check proxy access or use an offline archive.
if "%AWC_SOURCE_MODE%"=="online" echo [download] Public downloads require github.com and release-assets.githubusercontent.com access.
if "%AWC_FETCH_STATUS%"=="5" exit /b 1
if "%AWC_FETCH_STATUS%"=="6" exit /b 1
if "%AWC_FETCH_STATUS%"=="7" exit /b 1
if "%AWC_FETCH_STATUS%"=="28" exit /b 1
if "%AWC_FETCH_STATUS%"=="52" exit /b 1
if "%AWC_FETCH_STATUS%"=="55" exit /b 1
if "%AWC_FETCH_STATUS%"=="56" exit /b 1
if not "%AWC_FETCH_STATUS%"=="22" exit /b 2
if "%AWC_SOURCE_MODE%"=="restricted" if "%AWC_HTTP_STATUS%"=="401" exit /b 1
if "%AWC_SOURCE_MODE%"=="restricted" if "%AWC_HTTP_STATUS%"=="403" exit /b 1
if "%AWC_SOURCE_MODE%"=="restricted" if "%AWC_HTTP_STATUS%"=="407" exit /b 1
"%SystemRoot%\System32\findstr.exe" /x "404 408 429 500 502 503 504" "%AWC_STAGE%\http-status" >nul
if errorlevel 1 exit /b 2
exit /b 1
:help
echo AW Center Windows installation helper
echo Usage: AWCenter.cmd [wizard^|provision^|doctor^|start^|prepare-install-bundle] [options]
echo   provision --profile dev^|prod     Prepare the selected installation profile.
echo   doctor --profile dev^|prod        Read-only installation diagnosis.
echo   start --profile dev^|prod         Start an already provisioned profile.
echo   prepare-install-bundle --output PATH
echo   --repository HTTPS_URL_OR_DIR    Secondary reviewed-artifact mirror.
echo   --offline-dir DIR                Final fallback, including DIR\runtimes.
echo   --ca-file FILE                   Trusted CA certificate bundle.
echo   --source-mode online^|restricted^|corporate^|offline  Allowed acquisition sources; default online.
echo HTTPS_PROXY may be inherited from the process. URL credentials are not supported.
exit /b 0
:usage_error
echo [error] --repository, --offline-dir, --ca-file and --source-mode require a value.
exit /b 1
:source_mode_error
echo [error] --source-mode must be online, restricted, corporate or offline.
exit /b 1
:no_home
echo [error] LOCALAPPDATA is required for a user-scoped installation.
exit /b 1
:tools_missing
echo [error] Windows curl.exe, certutil.exe and tar.exe are required.
goto failed
:ca_error
echo [error] The explicitly supplied CA file is unavailable.
goto failed
:unsafe_home
echo [error] Existing installation ownership or permissions are unsafe. No repair was attempted.
goto failed
:insecure_repository
echo [error] Repository URLs must use HTTPS.
goto failed
:download_failed
echo [error] Download rejected or TLS verification failed. No source fallback was attempted.
goto failed
:integrity_error
echo [error] Bootstrap integrity verification failed. No unverified runtime was executed.
:failed
if defined AWC_STAGE_OWNED rd /s /q "%AWC_STAGE%" 2>nul
if defined AWC_PUSHD popd
if "%AWC_COMMAND%"=="" pause
exit /b 1
