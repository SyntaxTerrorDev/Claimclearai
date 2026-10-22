@echo off
setlocal
title ClaimClear launcher
cd /d "%~dp0"

set "SVC=%~dp0apps\extraction-service"
set "WEB=%~dp0apps\web"

echo.
echo  ===============================
echo   ClaimClear - local launcher
echo  ===============================
echo.

rem ---------- tools ----------
where node >nul 2>nul || goto :no_node

rem ---------- python environment for the extraction service ----------
set "PY="
if exist "%SVC%\ocr\Scripts\python.exe" set "PY=%SVC%\ocr\Scripts\python.exe"
if not defined PY if exist "%SVC%\.venv\Scripts\python.exe" set "PY=%SVC%\.venv\Scripts\python.exe"
if defined PY goto :have_py
where python >nul 2>nul || goto :no_python
echo [setup] Creating Python environment in apps\extraction-service\.venv ...
python -m venv "%SVC%\.venv" || goto :fail
set "PY=%SVC%\.venv\Scripts\python.exe"
:have_py
"%PY%" -c "import fastapi, uvicorn, pymupdf, pytesseract, google.genai, groq" >nul 2>nul && goto :py_ok
echo [setup] Installing Python packages (first run only) ...
"%PY%" -m pip install -q -r "%SVC%\requirements.txt" || goto :fail
:py_ok
echo [ok] Python: %PY%

rem ---------- web packages ----------
if exist "%WEB%\node_modules\next" goto :npm_ok
echo [setup] Installing web packages (first run only) ...
pushd "%WEB%"
call npm install || (popd & goto :fail)
popd
:npm_ok
echo [ok] Web packages installed

rem ---------- environment files ----------
if exist "%SVC%\.env" goto :env_ok
copy /y "%SVC%\.env.example" "%SVC%\.env" >nul
echo [setup] Created apps\extraction-service\.env from the example.
:env_ok
findstr /r /c:"^ *GEMINI_API_KEY *= *[^ ]" "%SVC%\.env" >nul 2>nul || goto :no_key
findstr /c:"Paste your gemini" "%SVC%\.env" >nul 2>nul && goto :no_key

rem Same random BACKEND_SECRET_TOKEN in both apps (web sends it, service checks it).
"%PY%" -c "import re,secrets,pathlib;P=pathlib.Path;s=P(r'%SVC%\.env');w=P(r'%WEB%\.env.local');t=s.read_text(encoding='utf-8');m=re.search(r'(?m)^BACKEND_SECRET_TOKEN=[\x22\x27]?([^\x22\x27\r\n]*)',t);tok=(m.group(1).strip() if m else '');ok=tok not in ('','change-me');tok=tok if ok else secrets.token_urlsafe(32);t=t if ok else re.sub(r'(?m)^BACKEND_SECRET_TOKEN=.*\n?','',t).rstrip()+chr(10)+'BACKEND_SECRET_TOKEN='+tok+chr(10);s.write_text(t,encoding='utf-8');w.write_text('EXTRACTION_SERVICE_URL=http://127.0.0.1:8000'+chr(10)+'BACKEND_SECRET_TOKEN='+tok+chr(10),encoding='utf-8')" || goto :fail
echo [ok] Environment files ready (API token in sync)

rem ---------- tesseract (only needed for scanned PDFs) ----------
where tesseract >nul 2>nul && goto :tess_ok
if exist "%ProgramFiles%\Tesseract-OCR\tesseract.exe" goto :tess_ok
echo [warn] Tesseract OCR not found: scanned PDFs will fail. Install with:
echo        winget install UB-Mannheim.TesseractOCR
goto :tess_done
:tess_ok
echo [ok] Tesseract OCR found
:tess_done

rem ---------- fresh demo documents (dates relative to today) ----------
"%PY%" "%~dp0samples\make_samples.py" >nul 2>nul && echo [ok] Sample PDFs ready in the samples folder

rem ---------- start servers ----------
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul && (echo [ok] Extraction service already running on port 8000) || (
  start "ClaimClear API (port 8000)" /d "%SVC%" cmd /k ""%PY%" -m uvicorn main:app --host 127.0.0.1 --port 8000"
  echo [..] Starting extraction service ...
)
netstat -ano | findstr /r /c:":3000 .*LISTENING" >nul && (echo [ok] Web app already running on port 3000) || (
  start "ClaimClear Web (port 3000)" /d "%WEB%" cmd /k "npm run dev"
  echo [..] Starting web app ...
)

echo [..] Waiting for both servers (first start can take ~30s) ...
powershell -NoProfile -Command "$u='http://127.0.0.1:8000/health','http://127.0.0.1:3000/upload'; foreach($x in $u){$ok=$false; for($i=0;$i -lt 120 -and -not $ok;$i++){try{Invoke-WebRequest -UseBasicParsing $x -TimeoutSec 3 | Out-Null; $ok=$true}catch{Start-Sleep 1}}; if(-not $ok){exit 1}}" || goto :not_up

echo.
echo  ClaimClear is running:  http://127.0.0.1:3000/upload
echo  Close the two server windows to stop it.
echo.
start "" "http://127.0.0.1:3000/upload"
timeout /t 5 >nul
exit /b 0

rem ---------- errors ----------
:no_node
echo [error] Node.js is not installed. Get it from https://nodejs.org (LTS), then run this again.
goto :fail
:no_python
echo [error] Python is not installed. Get it from https://www.python.org/downloads/ (tick "Add to PATH"), then run this again.
goto :fail
:no_key
echo [error] Add your Gemini API key to apps\extraction-service\.env  (GEMINI_API_KEY=...)
echo         Opening the file for you. Save it, then run start.bat again.
start "" notepad "%SVC%\.env"
goto :fail
:not_up
echo [error] A server did not start. Check the "ClaimClear API" and "ClaimClear Web" windows for the error.
goto :fail
:fail
echo.
pause
exit /b 1
