@echo off
if "%1"=="data" python pipeline.py --fresh
if "%1"=="update" python pipeline.py
if "%1"=="model" python model.py
if "%1"=="app" python app.py