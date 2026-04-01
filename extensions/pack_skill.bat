@echo off
REM 将 skills\ 下的指定 skill 打包为 ZIP 压缩包（可直接通过 Web 上传）
REM
REM 用法：
REM   pack_skill.bat <skill_name>    打包单个 skill（自动在 s1\s2 下搜索）
REM   pack_skill.bat -all            打包所有 skills

setlocal enabledelayedexpansion

set SCRIPT_DIR=%~dp0
set SKILLS_DIR=%SCRIPT_DIR%skills

if "%~1"=="" (
    echo 用法: %~nx0 ^<skill_name^>    打包单个 skill
    echo        %~nx0 -all            打包所有 skills
    echo.
    echo 可用的 skills:
    for /d %%S in ("%SKILLS_DIR%\*") do (
        for /d %%D in ("%%S\*") do (
            if exist "%%D\SKILL.md" echo   %%~nxD  ^(%%~nxS^)
        )
    )
    exit /b 1
)

if "%~1"=="-all" (
    echo 打包所有 skills...
    for /d %%S in ("%SKILLS_DIR%\*") do (
        for /d %%D in ("%%S\*") do (
            if exist "%%D\SKILL.md" call :pack_one "%%~nxD" "%%D"
        )
    )
    echo 全部完成!
    exit /b 0
)

REM 单个打包：在 s1\s2 子目录中搜索
for /d %%S in ("%SKILLS_DIR%\*") do (
    if exist "%%S\%~1\SKILL.md" (
        call :pack_one "%~1" "%%S\%~1"
        exit /b 0
    )
)
echo 错误: skill '%~1' 不存在（已搜索 s1\s2 子目录）
exit /b 1

:pack_one
set SKILL_NAME=%~1
set SKILL_PATH=%~2
set OUTPUT=%SCRIPT_DIR%%SKILL_NAME%.zip

python -c "import zipfile,os,sys;skill=sys.argv[1];src=sys.argv[2];out=sys.argv[3];zf=zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED);[zf.write(os.path.join(r,f),os.path.join(skill,os.path.relpath(os.path.join(r,f),src))) for r,ds,fs in os.walk(src) for f in fs];zf.close();print(f'已打包: {os.path.basename(out)}')" "%SKILL_NAME%" "%SKILL_PATH%" "%OUTPUT%"
exit /b 0
