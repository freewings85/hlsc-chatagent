@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
set "SKILLS_DIR=%SCRIPT_DIR%skills"
set "PYTHON_CMD="

call :find_python
if not defined PYTHON_CMD (
    echo ERROR: Python was not found. Install Python or use the py launcher.
    exit /b 1
)

if "%~1"=="" (
    echo Usage: %~nx0 [skill_name]
    echo        %~nx0 -all
    echo.
    echo Available skills:
    call :list_skills
    exit /b 1
)

if /i "%~1"=="-all" (
    echo Packing all skills...
    call :for_each_skill pack_one
    echo Done.
    exit /b 0
)

call :find_skill "%~1"
if defined FOUND_SKILL_PATH (
    call :pack_one "%~1" "%FOUND_SKILL_PATH%"
    exit /b %errorlevel%
)

echo ERROR: skill "%~1" was not found under "%SKILLS_DIR%".
exit /b 1

:find_python
where py >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=py -3"
    exit /b 0
)

where python >nul 2>nul
if not errorlevel 1 (
    set "PYTHON_CMD=python"
    exit /b 0
)

exit /b 1

:list_skills
for /d %%S in ("%SKILLS_DIR%\*") do (
    if exist "%%S\SKILL.md" (
        echo   %%~nxS
    ) else (
        for /d %%D in ("%%S\*") do (
            if exist "%%D\SKILL.md" echo   %%~nxD ^(%%~nxS^)
        )
    )
)
exit /b 0

:for_each_skill
set "CALLBACK=%~1"
for /d %%S in ("%SKILLS_DIR%\*") do (
    if exist "%%S\SKILL.md" (
        call :%CALLBACK% "%%~nxS" "%%S"
        if errorlevel 1 exit /b 1
    ) else (
        for /d %%D in ("%%S\*") do (
            if exist "%%D\SKILL.md" (
                call :%CALLBACK% "%%~nxD" "%%D"
                if errorlevel 1 exit /b 1
            )
        )
    )
)
exit /b 0

:find_skill
set "FOUND_SKILL_PATH="
for /d %%S in ("%SKILLS_DIR%\*") do (
    if /i "%%~nxS"=="%~1" if exist "%%S\SKILL.md" (
        set "FOUND_SKILL_PATH=%%S"
        exit /b 0
    )
    if exist "%%S\%~1\SKILL.md" (
        set "FOUND_SKILL_PATH=%%S\%~1"
        exit /b 0
    )
)
exit /b 0

:pack_one
set "SKILL_NAME=%~1"
set "SKILL_PATH=%~2"
set "OUTPUT=%SCRIPT_DIR%%SKILL_NAME%.zip"

%PYTHON_CMD% -c "import os, sys, zipfile; skill = sys.argv[1]; src = sys.argv[2]; out = sys.argv[3]; zf = zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED); [zf.write(os.path.join(root, name), os.path.join(skill, os.path.relpath(os.path.join(root, name), src))) for root, _, files in os.walk(src) for name in files]; zf.close(); print('Packed: ' + os.path.basename(out))" "%SKILL_NAME%" "%SKILL_PATH%" "%OUTPUT%"
if errorlevel 1 exit /b 1
exit /b 0
