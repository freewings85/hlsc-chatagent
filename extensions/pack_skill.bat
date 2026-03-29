@echo off
REM 将 skills\ 下的指定 skill 打包为 ZIP 压缩包（可直接通过 Web 上传）
REM
REM 用法：
REM   pack_skill.bat <skill_name>    打包单个 skill
REM   pack_skill.bat -all            打包所有 skills

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set SKILLS_DIR=%SCRIPT_DIR%skills

if "%~1"=="" (
    echo 用法: %~nx0 ^<skill_name^>    打包单个 skill
    echo        %~nx0 -all            打包所有 skills
    echo.
    echo 可用的 skills:
    dir /b "%SKILLS_DIR%"
    exit /b 1
)

if "%~1"=="-all" (
    echo 打包所有 skills...
    for /d %%D in ("%SKILLS_DIR%\*") do (
        call :pack_one "%%~nxD"
    )
    echo 全部完成!
    exit /b 0
)

call :pack_one "%~1"
exit /b %errorlevel%

:pack_one
set SKILL_NAME=%~1
set SKILL_PATH=%SKILLS_DIR%\%SKILL_NAME%

if not exist "%SKILL_PATH%" (
    echo 错误: skill '%SKILL_NAME%' 不存在
    exit /b 1
)

if not exist "%SKILL_PATH%\SKILL.md" (
    echo 错误: skill '%SKILL_NAME%' 缺少 SKILL.md
    exit /b 1
)

set OUTPUT=%SCRIPT_DIR%%SKILL_NAME%.zip

python -c "import zipfile,os,sys;skill=sys.argv[1];src=sys.argv[2];out=sys.argv[3];zf=zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED);[zf.write(os.path.join(r,f),os.path.join(skill,os.path.relpath(os.path.join(r,f),src))) for r,ds,fs in os.walk(src) for f in fs];zf.close();print(f'已打包: {os.path.basename(out)}')" "%SKILL_NAME%" "%SKILL_PATH%" "%OUTPUT%"
exit /b 0
