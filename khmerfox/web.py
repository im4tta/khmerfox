"""Modern Flask web UI for KhmerFox with Khmer styling."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import re
import threading
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request, send_from_directory

from khmerfox.core import AVAILABLE_FIELDS, DATA_DIR, Config, GmapsScraper, export_places

app = Flask(__name__)

MAX_LOGS = 1000
_lock = threading.Lock()
_state = {
    "running": False,
    "config": None,
    "paths": [],
    "error": None,
    "started_at": None,
    "finished_at": None,
    "places_found": 0,
    "places_scraped": 0,
    "places_data": [],
    "stop_event": None,
}
_logs: list[str] = []


class _MemHandler(logging.Handler):
    def emit(self, record):
        global _logs
        msg = self.format(record)
        with _lock:
            _logs.append(msg)
            if len(_logs) > MAX_LOGS:
                _logs.pop(0)


HTML = r"""
<!DOCTYPE html>
<html lang="km" data-theme="light">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>KhmerFox — Cambodia Maps Scraper</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Noto+Sans+Khmer:wght@400;700&display=swap" rel="stylesheet">
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Cdefs%3E%3ClinearGradient id='g' x1='0%25' y1='0%25' x2='100%25' y2='100%25'%3E%3Cstop offset='0%25' stop-color='%23e31c25'/%3E%3Cstop offset='100%25' stop-color='%23b9131b'/%3E%3C/linearGradient%3E%3C/defs%3E%3Crect width='32' height='32' rx='8' fill='url(%23g)'/%3E%3Ctext x='16' y='22' text-anchor='middle' fill='white' font-family='Arial,sans-serif' font-size='16' font-weight='bold'%3EKF%3C/text%3E%3C/svg%3E">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/gridstack@10/dist/gridstack.min.css" />
<style>
:root{--khmer-red:#e31c25;--khmer-red-dark:#b9131b;--khmer-blue:#032ea1;--khmer-blue-light:#1a4bc4;--angkor-gold:#c9a227;--bg:#f8f6f1;--surface:#ffffff;--surface-2:#f3f1eb;--text:#1c1917;--text-2:#57534e;--text-3:#a8a29e;--border:#e7e5e4;--shadow:0 1px 3px rgba(0,0,0,0.05),0 12px 32px rgba(3,46,161,0.08);--radius:16px;--radius-sm:10px;--success:#15803d;--success-bg:#dcfce7;--error:#b91c1c;--error-bg:#fee2e2;--warning:#a16207;--warning-bg:#fef9c3;}
[data-theme="dark"]{--bg:#0c0a09;--surface:#1c1917;--surface-2:#292524;--text:#fafaf9;--text-2:#a8a29e;--text-3:#78716c;--border:#44403c;--shadow:0 1px 3px rgba(0,0,0,0.3),0 12px 32px rgba(0,0,0,0.4);--success:#22c55e;--success-bg:#14532d;--error:#ef4444;--error-bg:#7f1d1d;--warning:#eab308;--warning-bg:#713f12;}
*{box-sizing:border-box}
body{margin:0;font-family:'Inter','Noto Sans Khmer',-apple-system,BlinkMacSystemFont,sans-serif;background:var(--bg);color:var(--text);line-height:1.5;transition:background .2s,color .2s;}
.navbar{background:var(--surface);border-bottom:1px solid var(--border);position:sticky;top:0;z-index:100;}
.navbar-inner{max-width:1200px;margin:0 auto;padding:.875rem 1.5rem;display:flex;align-items:center;justify-content:space-between;}
.brand{display:flex;align-items:center;gap:.75rem;text-decoration:none;}
.brand-icon{width:38px;height:38px;background:linear-gradient(135deg,var(--khmer-red),var(--khmer-red-dark));border-radius:10px;display:grid;place-items:center;color:#fff;font-weight:700;font-size:1.1rem;box-shadow:0 4px 12px rgba(227,28,37,.25);}
.brand-text{display:flex;flex-direction:column}
.brand-title{font-size:1.15rem;font-weight:700;color:var(--text);line-height:1.2}
.brand-sub{font-size:.75rem;color:var(--text-3);line-height:1.2}
.nav-actions{display:flex;gap:.5rem}
.icon-btn{width:38px;height:38px;border:1px solid var(--border);background:var(--surface-2);border-radius:10px;cursor:pointer;display:grid;place-items:center;color:var(--text-2);transition:all .15s;}
.icon-btn:hover{background:var(--border);color:var(--text)}
main{max-width:1200px;margin:0 auto;padding:2rem 1.5rem 4rem}
.hero{margin-bottom:2rem}
.hero h1{margin:0 0 .5rem;font-size:clamp(1.75rem,4vw,2.5rem);font-weight:700;letter-spacing:-.02em;}
.hero h1 span{color:var(--khmer-red)}
.hero p{margin:0;color:var(--text-2);font-size:1.05rem}
.grid-stack{background:transparent;}
.grid-stack-item-content{border-radius:var(--radius);background:none;}
.grid-stack-item-content>.card{height:100%;margin:0;display:flex;flex-direction:column;}
.card-body-grow{flex:1;overflow:auto;min-height:0;display:flex;flex-direction:column;}
.card-body-scroll{overflow-y:auto;}
.card{background:var(--surface);border-radius:var(--radius);box-shadow:var(--shadow);border:1px solid var(--border);overflow:hidden;}
.card-header{padding:1.25rem 1.5rem;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between;gap:1rem;}
.card-title{margin:0;font-size:1rem;font-weight:600;display:flex;align-items:center;gap:.5rem;}
.card-body{padding:1.5rem}
.form-group{margin-bottom:1.25rem}
.form-group:last-child{margin-bottom:0}
label{display:block;font-size:.8125rem;font-weight:600;color:var(--text-2);margin-bottom:.4rem;}
.label-hint{font-weight:400;color:var(--text-3);margin-left:.25rem}
input,select{width:100%;padding:.7rem .9rem;border:1px solid var(--border);border-radius:var(--radius-sm);background:var(--surface);color:var(--text);font-size:.9375rem;transition:all .15s;font-family:inherit;}
input:focus,select:focus{outline:none;border-color:var(--khmer-blue);box-shadow:0 0 0 3px rgba(3,46,161,.1);}
.form-row{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
.checks{display:flex;gap:1.25rem;flex-wrap:wrap}
.field-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:.5rem .75rem;max-height:220px;overflow:auto;padding:.75rem;background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius-sm);}
@media(min-width:640px){.field-grid{grid-template-columns:repeat(3,1fr)}}
.field-grid .check{font-size:.8125rem;margin:0}
.field-grid .check input{width:1rem;height:1rem}
.field-actions{display:flex;gap:.5rem;margin-top:.5rem;justify-content:flex-end}
.field-actions button{font-size:.75rem;padding:.35rem .6rem}
.check{display:flex;align-items:center;gap:.5rem;cursor:pointer;font-size:.9375rem;color:var(--text-2);}
.check input{width:1.15rem;height:1.15rem;accent-color:var(--khmer-red);cursor:pointer;}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:.5rem;padding:.75rem 1.25rem;border:none;border-radius:var(--radius-sm);font-size:.9375rem;font-weight:600;cursor:pointer;transition:all .15s;}
.btn:disabled{opacity:.6;cursor:not-allowed}
.btn-primary{background:var(--khmer-red);color:#fff;box-shadow:0 4px 14px rgba(227,28,37,.25);}
.btn-primary:hover:not(:disabled){background:var(--khmer-red-dark);transform:translateY(-1px)}
.btn-secondary{background:var(--surface-2);color:var(--text);border:1px solid var(--border);}
.btn-secondary:hover:not(:disabled){background:var(--border)}
.btn-danger{background:var(--error);color:#fff;box-shadow:0 4px 14px rgba(185,28,28,.25);}
.btn-danger:hover:not(:disabled){background:#991b1b;transform:translateY(-1px)}
.btn-sm{padding:.5rem .875rem;font-size:.875rem}
.status-panel{display:grid;grid-template-columns:repeat(2,1fr);gap:1rem;margin-bottom:1.5rem;}
.stat-card{background:var(--surface-2);border:1px solid var(--border);border-radius:var(--radius-sm);padding:1rem;}
.stat-label{font-size:.75rem;font-weight:600;color:var(--text-3);text-transform:uppercase;letter-spacing:.05em;margin-bottom:.25rem;}
.stat-value{font-size:1.5rem;font-weight:700;color:var(--text)}
.progress-wrap{margin-bottom:.5rem}
.progress-bar-bg{height:8px;background:var(--surface-2);border-radius:999px;overflow:hidden;}
.progress-bar-fill{height:100%;width:0%;background:linear-gradient(90deg,var(--khmer-red),var(--angkor-gold));border-radius:999px;transition:width .4s ease;}
.progress-bar-fill.indeterminate{width:40%;animation:indeterminate 1.2s ease-in-out infinite alternate;}
@keyframes indeterminate{0%{transform:translateX(-100%)}100%{transform:translateX(250%)}}
.progress-meta{display:flex;justify-content:space-between;margin-top:.5rem;font-size:.8125rem;color:var(--text-2);}
.status-badge{display:inline-flex;align-items:center;gap:.4rem;padding:.35rem .85rem;border-radius:999px;font-size:.75rem;font-weight:700;text-transform:uppercase;letter-spacing:.03em;}
.status-idle{background:var(--surface-2);color:var(--text-2)}
.status-run{background:var(--khmer-red);color:#fff}
.status-ok{background:var(--success);color:#fff}
.status-err{background:var(--error);color:#fff}
.logs-toolbar{display:flex;gap:.5rem;margin-bottom:.75rem;justify-content:flex-end}
.logs{background:#0f0e0d;color:#e7e5e4;border-radius:var(--radius-sm);padding:1rem;flex:1;min-height:100px;overflow:auto;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:.8125rem;line-height:1.6;white-space:pre-wrap;}
.logs:empty::before{content:"Logs will appear here once scraping starts...";color:#78716c;}
.log-line{margin:0;padding:.15rem 0}
.log-line.error{color:#fca5a5}
.log-line.warning{color:#fde047}
.log-line.info{color:#93c5fd}
.log-line.debug{color:#d6d3d1}
.results-empty{text-align:center;padding:3rem 1rem;color:var(--text-3);}
.results-empty svg{width:64px;height:64px;margin-bottom:1rem;opacity:.5}
table{width:100%;border-collapse:collapse;font-size:.875rem}
th,td{padding:.875rem 1rem;text-align:left;border-bottom:1px solid var(--border);}
th{font-weight:600;color:var(--text-2);background:var(--surface-2);position:sticky;top:0;}
tr:hover td{background:var(--surface-2)}
.file-type{display:inline-flex;align-items:center;padding:.2rem .5rem;border-radius:6px;font-size:.75rem;font-weight:700;text-transform:uppercase;}
.type-csv{background:#dbeafe;color:#1e40af}
.type-json{background:#fef3c7;color:#92400e}
.type-md{background:#f3e8ff;color:#6b21a8}
.type-xlsx{background:#dcfce7;color:#166534}
[data-theme="dark"] .type-csv{background:#1e3a8a;color:#bfdbfe}
[data-theme="dark"] .type-json{background:#78350f;color:#fde68a}
[data-theme="dark"] .type-md{background:#581c87;color:#e9d5ff}
[data-theme="dark"] .type-xlsx{background:#14532d;color:#bbf7d0}
.file-size{color:var(--text-3);font-variant-numeric:tabular-nums}
.file-date{color:var(--text-2)}
.toast-container{position:fixed;bottom:1.5rem;right:1.5rem;display:flex;flex-direction:column;gap:.75rem;z-index:1000;}
.toast{background:var(--surface);color:var(--text);border:1px solid var(--border);border-radius:var(--radius-sm);padding:.875rem 1.25rem;box-shadow:var(--shadow);display:flex;align-items:center;gap:.75rem;animation:slideIn .25s ease;min-width:280px;}
.toast.success{border-left:4px solid var(--success)}
.toast.error{border-left:4px solid var(--error)}
.toast.info{border-left:4px solid var(--khmer-blue)}
@keyframes slideIn{from{transform:translateX(120%);opacity:0}to{transform:translateX(0);opacity:1}}
footer{text-align:center;padding:2rem;color:var(--text-3);font-size:.8125rem;}
.spinner{width:16px;height:16px;border:2px solid rgba(255,255,255,.3);border-top-color:#fff;border-radius:50%;animation:spin .8s linear infinite;}
@keyframes spin{to{transform:rotate(360deg)}}
.map-wrap{flex:1;min-height:200px;border-radius:var(--radius-sm);overflow:hidden;margin-top:1rem;display:none;border:1px solid var(--border);}
.map-wrap.active{display:block}
.map-wrap .leaflet-container{height:100%;width:100%;background:var(--surface);}
.map-popup h3{margin:0 0 .25rem;font-size:.9375rem;color:var(--text)}
.map-popup p{margin:0;color:var(--text-2);font-size:.8125rem}
.map-popup a{color:var(--khmer-blue);text-decoration:none}
.map-popup .popup-rating{font-size:.8125rem;color:var(--text-3)}
.view-toggle{display:flex;gap:.5rem}
.view-toggle .btn.active{background:var(--khmer-blue);color:#fff;border-color:var(--khmer-blue)}
.btn-pin.active{background:var(--khmer-blue);color:#fff;border-color:var(--khmer-blue)}
</style>
</head>
<body>
<nav class="navbar">
  <div class="navbar-inner">
    <a class="brand" href="/">
      <div class="brand-icon">KF</div>
      <div class="brand-text">
        <span class="brand-title">KhmerFox</span>
        <span class="brand-sub">Cambodia Maps Scraper</span>
      </div>
    </a>
    <div class="nav-actions">
      <button class="icon-btn" id="themeToggle" title="Toggle theme">🌓</button>
    </div>
  </div>
</nav>

<main>
  <div class="hero">
    <h1>Scrape Google Maps for <span>Cambodia</span></h1>
    <p>ឧបករណ៍ស្កេន Google Maps សម្រាប់ប្រទេសកម្ពុជា — Khmer & English business listings.</p>
  </div>

  <div class="grid-stack">
    <div class="grid-stack-item" gs-w="4" gs-h="12">
      <div class="grid-stack-item-content">
        <div class="card">
          <div class="card-header">
            <h2 class="card-title">⚙️ Settings</h2>
            <span class="status-badge status-idle" id="statusBadge">Idle</span>
          </div>
          <div class="card-body card-body-scroll">
            <div class="form-group">
              <label for="q">Search query <span class="label-hint">/ ពាក្យស្វែងរក</span></label>
              <input id="q" class="kh" value="ហាងកាហ្វេនៅភ្នំពេញ" placeholder="e.g. hotels in Siem Reap">
            </div>
            <div class="form-group">
              <label for="fmt">Output format</label>
              <select id="fmt">
                <option value="csv">CSV (Excel-safe)</option>
                <option value="json">JSON</option>
                <option value="md">Markdown</option>
                <option value="xlsx">Excel (.xlsx)</option>
                <option value="all">All formats</option>
              </select>
            </div>
            <div class="form-group">
              <label>Output fields</label>
              <div class="field-grid" id="fieldGrid">
                {% for field, label, default in fields %}
                <label class="check" title="{{ field }}"><input type="checkbox" value="{{ field }}" {% if default %}checked{% endif %}> {{ label }}</label>
                {% endfor %}
              </div>
              <div class="field-actions">
                <button type="button" class="btn btn-secondary btn-sm" id="selectAllFields">All</button>
                <button type="button" class="btn btn-secondary btn-sm" id="selectDefaultFields">Default</button>
                <button type="button" class="btn btn-secondary btn-sm" id="clearFields">None</button>
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label for="max">Max results <span class="label-hint">(0 = unlimited)</span></label>
                <input id="max" type="number" value="0" min="0">
              </div>
              <div class="form-group">
                <label for="conc">Concurrency</label>
                <input id="conc" type="number" value="4" min="1" max="8">
              </div>
            </div>
            <div class="form-row">
              <div class="form-group">
                <label for="log">Log level</label>
                <select id="log">
                  <option>INFO</option>
                  <option>DEBUG</option>
                  <option>WARNING</option>
                  <option>ERROR</option>
                </select>
              </div>
              <div class="form-group">
                <label for="proxy">Proxy <span class="label-hint">(optional)</span></label>
                <input id="proxy" placeholder="http://127.0.0.1:8080">
              </div>
            </div>
            <div class="form-group">
              <div class="checks">
                <label class="check"><input type="checkbox" id="headless" checked> Headless browser</label>
                <label class="check"><input type="checkbox" id="shots"> Save screenshots</label>
              </div>
            </div>
            <div style="display:flex;gap:.75rem;margin-top:1.5rem;flex-wrap:wrap;">
              <button id="start" class="btn btn-primary">🚀 Start Scrape</button>
              <button id="stop" class="btn btn-danger" disabled>⏹ Stop</button>
              <button id="refresh" class="btn btn-secondary btn-sm">↻ Refresh</button>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="grid-stack-item" gs-w="8" gs-h="4">
      <div class="grid-stack-item-content">
        <div class="card">
          <div class="card-header">
            <h2 class="card-title">📊 Progress</h2>
            <span id="statusText" class="file-size">Ready</span>
          </div>
          <div class="card-body">
            <div class="status-panel">
              <div class="stat-card">
                <div class="stat-label">Places Found</div>
                <div class="stat-value" id="statFound">0</div>
              </div>
              <div class="stat-card">
                <div class="stat-label">Scraped</div>
                <div class="stat-value" id="statScraped">0</div>
              </div>
            </div>
            <div class="progress-wrap">
              <div class="progress-bar-bg">
                <div class="progress-bar-fill" id="progressFill"></div>
              </div>
              <div class="progress-meta">
                <span id="progressPercent">0%</span>
                <span id="progressTime">—</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
    <div class="grid-stack-item" gs-w="8" gs-h="7">
      <div class="grid-stack-item-content">
        <div class="card">
          <div class="card-header">
            <h2 class="card-title">📜 Live Logs</h2>
            <div class="logs-toolbar">
              <button class="btn btn-secondary btn-sm btn-pin active" id="logPin" title="Auto-scroll to bottom">📌</button>
              <button class="btn btn-secondary btn-sm" id="copyLogs">Copy</button>
              <button class="btn btn-secondary btn-sm" id="clearLogs">Clear</button>
            </div>
          </div>
          <div class="card-body card-body-grow" style="padding-top:0;">
            <div class="logs" id="logs"></div>
          </div>
        </div>
      </div>
    </div>
    <div class="grid-stack-item" gs-w="8" gs-h="9">
      <div class="grid-stack-item-content">
        <div class="card">
          <div class="card-header">
            <h2 class="card-title">📁 Results</h2>
            <div class="view-toggle" id="viewToggle">
              <button class="btn btn-secondary btn-sm active" data-view="table">Table</button>
              <button class="btn btn-secondary btn-sm" data-view="map">Map</button>
            </div>
          </div>
          <div class="card-body card-body-grow">
            <div id="resultsTable">
              <div class="results-empty">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/></svg>
                <p>No results yet. Run a scrape to generate files.</p>
              </div>
            </div>
            <div class="map-wrap" id="mapWrap"><div id="map"></div></div>
          </div>
        </div>
      </div>
    </div>
  </div>
</main>

<div class="toast-container" id="toasts"></div>

<footer>
  KhmerFox · Cambodia-focused Google Maps scraper powered by Camoufox
</footer>

<script src="https://cdn.jsdelivr.net/npm/gridstack@10/dist/gridstack-all.js"></script>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const $=id=>document.getElementById(id);
let iv=null,startedAt=null;

// Theme
try{
  const saved=localStorage.getItem('kf-theme')||'light';
  document.documentElement.setAttribute('data-theme',saved);
  $('themeToggle').onclick=()=>{
    const cur=document.documentElement.getAttribute('data-theme');
    const next=cur==='dark'?'light':'dark';
    document.documentElement.setAttribute('data-theme',next);
    localStorage.setItem('kf-theme',next);
  };
}catch(e){}

function toast(msg,type='info',duration=4000){
  const t=document.createElement('div');
  t.className='toast '+type;
  t.innerHTML='<span>'+msg+'</span>';
  $('toasts').appendChild(t);
  setTimeout(()=>t.remove(),duration);
}

function setStatus(state,text){
  const b=$('statusBadge');
  b.className='status-badge status-'+state;
  b.textContent=state==='run'?'Running':state==='ok'?'Done':state==='err'?'Error':'Idle';
  $('statusText').textContent=text;
}

function setProgress(pct,indeterminate=false){
  const f=$('progressFill');
  f.classList.toggle('indeterminate',indeterminate);
  if(!indeterminate) f.style.width=pct+'%';
  $('progressPercent').textContent=indeterminate?'In progress...':pct+'%';
}

function formatDuration(ms){
  if(ms<60000) return Math.round(ms/1000)+'s';
  const m=Math.floor(ms/60000),s=Math.round((ms%60000)/1000);
  return m+'m '+s+'s';
}

function parseLevel(line){
  const m=line.match(/\[(DEBUG|INFO|WARNING|ERROR)\]/i);
  return m?m[1].toLowerCase():'debug';
}

let lastLogCount=0, logPin=true;
function appendLogs(lines){
  if(!lines.length) return;
  const box=$('logs');
  const wasPinned=logPin&&box.scrollTop>=box.scrollHeight-box.clientHeight-10;
  const frag=document.createDocumentFragment();
  lines.forEach(line=>{
    const p=document.createElement('div');
    p.className='log-line '+parseLevel(line);
    p.textContent=line;
    frag.appendChild(p);
  });
  box.appendChild(frag);
  if(logPin&&wasPinned) box.scrollTop=box.scrollHeight;
}
$('logPin').onclick=()=>{
  logPin=!logPin;
  $('logPin').classList.toggle('active',logPin);
  if(logPin){const b=$('logs');b.scrollTop=b.scrollHeight;}
};

async function fetchStatus(){
  const d=await fetch('/status').then(r=>r.json());
  $('statFound').textContent=d.places_found||0;
  $('statScraped').textContent=d.places_scraped||0;

  if(d.running){
    setStatus('run','Scraping in progress...');
    setProgress(0,true);
    startedAt=startedAt||new Date(d.started_at);
    $('progressTime').textContent='Elapsed '+formatDuration(Date.now()-startedAt);
    $('start').disabled=true;
    $('start').innerHTML='<span class="spinner"></span> Running';
    $('stop').disabled=false;
    $('stop').innerHTML='⏹ Stop';
  }else if(d.error){
    setStatus('err','Error: '+d.error);
    setProgress(0,false);
    $('progressTime').textContent='Failed';
    $('start').disabled=false;
    $('start').innerHTML='🚀 Start Scrape';
    $('stop').disabled=true;
    $('stop').innerHTML='⏹ Stop';
    stopPolling();
    if(d.logs && d.logs.length!==lastLogCount) toast('Scrape failed','error');
  }else if(d.finished_at){
    setStatus('ok','Saved '+d.places_scraped+' places');
    setProgress(100,false);
    $('progressTime').textContent='Finished';
    $('start').disabled=false;
    $('start').innerHTML='🚀 Start Scrape';
    $('stop').disabled=true;
    $('stop').innerHTML='⏹ Stop';
    stopPolling();
    if(d.logs && d.logs.length!==lastLogCount) toast('Scrape complete!','success');
    loadResults();
  }else{
    setStatus('idle','Ready');
    setProgress(0,false);
    $('progressTime').textContent='—';
    $('start').disabled=false;
    $('start').innerHTML='🚀 Start Scrape';
    $('stop').disabled=true;
    $('stop').innerHTML='⏹ Stop';
  }

  if(d.logs){
    if(d.logs.length>lastLogCount){
      appendLogs(d.logs.slice(lastLogCount));
      lastLogCount=d.logs.length;
    }
  }
}

function startPolling(){
  if(!iv) iv=setInterval(fetchStatus,1000);
}
function stopPolling(){
  if(iv){clearInterval(iv);iv=null;}
  startedAt=null;
}

async function loadResults(){
  const d=await fetch('/results').then(r=>r.json());
  const box=$('resultsTable');
  if(!d.files.length){
    box.innerHTML='<div class="results-empty"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z"/></svg><p>No results yet. Run a scrape to generate files.</p></div>';
    return;
  }
  box.innerHTML='<div style="overflow:auto;max-height:420px;"><table><thead><tr><th>File</th><th>Type</th><th>Size</th><th>Modified</th><th></th></tr></thead><tbody>'+
    d.files.map(f=>'<tr><td>'+escapeHtml(f.name)+'</td><td><span class="file-type type-'+f.type+'">'+f.type+'</span></td><td class="file-size">'+formatBytes(f.size)+'</td><td class="file-date">'+new Date(f.modified).toLocaleString()+'</td><td style="white-space:nowrap"><a class="btn btn-secondary btn-sm" href="/download/'+encodeURIComponent(f.name)+'" download>Download</a><button class="btn btn-secondary btn-sm btn-map" data-file="'+escapeHtml(f.name)+'" title="View on map">🗺</button></td></tr>').join('')+
    '</tbody></table></div>';
  updateMap();
}

function formatBytes(n){
  if(n<1024) return n+' B';
  if(n<1024*1024) return (n/1024).toFixed(1)+' KB';
  return (n/(1024*1024)).toFixed(1)+' MB';
}

function escapeHtml(s){
  return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function getSelectedFields(){
  return Array.from($('fieldGrid').querySelectorAll('input:checked')).map(i=>i.value);
}

$('selectAllFields').onclick=()=>{
  $('fieldGrid').querySelectorAll('input').forEach(i=>i.checked=true);
};
$('selectDefaultFields').onclick=()=>{
  $('fieldGrid').querySelectorAll('input').forEach(i=>{
    i.checked=i.getAttribute('checked')==='checked';
  });
};
$('clearFields').onclick=()=>{
  $('fieldGrid').querySelectorAll('input').forEach(i=>i.checked=false);
};

$('start').onclick=async()=>{
  const q=$('q').value.trim();
  if(!q){toast('Please enter a search query','error');$('q').focus();return;}
  const selectedFields=getSelectedFields();
  if(!selectedFields.length){toast('Please select at least one output field','error');return;}
  $('logs').innerHTML='';
  lastLogCount=0;
  startedAt=null;
  setStatus('idle','Starting...');
  setProgress(0,false);
  $('start').disabled=true;
  $('start').innerHTML='<span class="spinner"></span> Starting...';
  $('stop').disabled=false;
  const r=await fetch('/scrape',{
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({
      query:q,
      format:$('fmt').value,
      max_results:+$('max').value,
      concurrency:+$('conc').value,
      log_level:$('log').value,
      proxy:$('proxy').value.trim(),
      headless:$('headless').checked,
      screenshots:$('shots').checked,
      fields:selectedFields
    })
  });
  if(!r.ok){
    const e=await r.json();
    toast(e.error||'Failed to start scrape','error');
    setStatus('err',e.error||'Failed');
    $('start').disabled=false;
    $('start').innerHTML='🚀 Start Scrape';
    return;
  }
  toast('Scrape started','info');
  startPolling();
};

$('stop').onclick=async()=>{
  $('stop').disabled=true;
  $('stop').innerHTML='<span class="spinner"></span> Stopping...';
  try{
    const r=await fetch('/stop',{method:'POST'});
    const d=await r.json();
    toast(d.status==='stopping'?'Scrape stopping...':'No scrape running','info');
  }catch(e){
    toast('Failed to send stop signal','error');
  }
};

$('refresh').onclick=()=>{loadResults();toast('Results refreshed','success');};

$('copyLogs').onclick=()=>{
  const text=$('logs').innerText;
  if(!text){toast('No logs to copy','error');return;}
  navigator.clipboard.writeText(text).then(()=>toast('Logs copied','success'));
};

$('clearLogs').onclick=()=>{
  $('logs').innerHTML='';
  lastLogCount=0;
  toast('Logs cleared','info');
};

fetchStatus();
loadResults();

// Map
let map=null,markers=null;
function initMap(){
  if(!map){
    const el=$('map');
    if(!el.offsetHeight) el.style.minHeight='300px';
    map=L.map('map',{zoomControl:true}).setView([11.56,104.92],6);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',{
      maxZoom:20,
      attribution:'&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> &copy; <a href="https://carto.com/">CARTO</a>'
    }).addTo(map);
    setTimeout(()=>map.invalidateSize(),50);
  }
}
function updateMap(){
  if(markers){map.removeLayer(markers);markers=null;}
  fetch('/places-data').then(r=>r.json()).then(data=>{
    const places=data.places||[];
    console.log('KhmerFox map data:',places.length,'places, sample:',places.slice(0,2));
    if(!places.length){toast('No scraped data to map — run a scrape first','info');return;}
    const hasCoords=places.filter(p=>p.latitude&&p.longitude);
    console.log('KhmerFox coords:',hasCoords.length,'with lat/lng');
    if(!hasCoords.length){toast('No coordinates in scraped data (latitude/longitude empty)','info');return;}
    toast('Placing '+hasCoords.length+' pins on map','info',2000);
    initMap();
    markers=L.featureGroup(hasCoords.map(p=>{
      const r=parseFloat(p.rating);
      const color=r>=4?'#15803d':r>=3?'#c9a227':'#e31c25';
      const icon=L.divIcon({
        html:`<div style="background:${color};color:#fff;width:32px;height:32px;border-radius:50%;display:grid;place-items:center;font-size:.75rem;font-weight:700;border:3px solid #fff;box-shadow:0 2px 8px rgba(0,0,0,.3);">${p.rating||'?'}</div>`,
        className:'',iconSize:[32,32],iconAnchor:[16,16]
      });
      return L.marker([+p.latitude,+p.longitude],{icon}).bindPopup(
        `<div class="map-popup"><h3>${escapeHtml(p.name)}</h3>`+
        (p.rating?`<div class="popup-rating">★ ${p.rating}${p.reviews?' · '+p.reviews+' reviews':''}</div>`:'')+
        (p.address?`<p>${escapeHtml(p.address)}</p>`:'')+
        (p.maps_url?`<a href="${p.maps_url}" target="_blank">Open in Google Maps →</a>`:'')+
        '</div>'
      );
    }));
    markers.addTo(map);
    if(hasCoords.length===1){
      map.setView([+hasCoords[0].latitude,+hasCoords[0].longitude],15);
    }else{
      map.fitBounds(markers.getBounds().pad(0.1));
    }
  }).catch(e=>toast('Map error: '+e.message,'error'));
}
$('viewToggle').addEventListener('click',e=>{
  const btn=e.target.closest('[data-view]');
  if(!btn) return;
  $('viewToggle').querySelectorAll('.btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  if(btn.dataset.view==='map'){
    $('mapWrap').classList.add('active');
    $('resultsTable').style.display='none';
    requestAnimationFrame(()=>{initMap();updateMap();setTimeout(()=>map&&map.invalidateSize(),150);});
  }else{
    $('mapWrap').classList.remove('active');
    $('resultsTable').style.display='';
  }
});
// GridStack — draggable & resizable dashboard
const grid=GridStack.init({
  column:12,cellHeight:60,margin:10,float:true,minRow:1,
  animate:true,handle:'.card-header',
  draggable:{handle:'.card-header',scroll:false,appendTo:'body'},
  resizable:{handles:'se'}
});
grid.on('resizestop',(e,el)=>{
  if(el.querySelector('#map')){initMap();setTimeout(()=>map&&map.invalidateSize(),200);}
  if(el.querySelector('.logs')) setTimeout(()=>el.querySelector('.logs').scrollTop=el.querySelector('.logs').scrollHeight,100);
});
window.addEventListener('resize',()=>setTimeout(()=>grid?.compact(),300));
// Persist layout
grid.on('change',()=>{
  try{localStorage.setItem('kf-grid',JSON.stringify(grid.save(false)));}catch(_){}
});
try{
  const saved=localStorage.getItem('kf-grid');
  if(saved) setTimeout(()=>grid.load(JSON.parse(saved)),100);
}catch(_){}

// Delegate Map buttons in results table
$('resultsTable').addEventListener('click',e=>{
  const btn=e.target.closest('.btn-map');
  if(!btn) return;
  $('viewToggle').querySelector('[data-view="map"]').click();
});
</script>
</body>
</html>
"""


def _reset_state(config: Config):
    global _state, _logs
    with _lock:
        _state.update(
            {
                "running": True,
                "config": config,
                "paths": [],
                "error": None,
                "started_at": datetime.now().isoformat(),
                "finished_at": None,
                "places_found": 0,
                "places_scraped": 0,
                "places_data": [],
                "stop_event": asyncio.Event(),
            }
        )
        _logs.clear()


def _finish(paths: list[Path] | None = None, error: str | None = None):
    global _state
    with _lock:
        _state.update(
            {
                "running": False,
                "paths": [str(p) for p in (paths or [])],
                "error": error,
                "finished_at": datetime.now().isoformat(),
            }
        )


async def _worker(config: Config):
    _reset_state(config)
    handler = _MemHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", "%H:%M:%S"))
    root = logging.getLogger()
    root.setLevel(getattr(logging, config.log_level))
    root.addHandler(handler)

    def bump():
        with _lock:
            _state["places_scraped"] += 1

    with _lock:
        stop_event = _state.get("stop_event")

    try:
        places = await GmapsScraper(config, progress_callback=bump, stop_event=stop_event).run()
        with _lock:
            _state["places_found"] = len(places)
            _state["places_scraped"] = len(places)
        paths = export_places(places, config.query, config.output_format, config.fields)
        with _lock:
            _state["places_data"] = [p.to_dict() for p in places]
        _finish(paths=paths)
    except Exception as exc:
        logging.exception("Scrape failed")
        _finish(error=str(exc))
    finally:
        root.removeHandler(handler)


@app.route("/")
def index():
    return render_template_string(HTML, fields=AVAILABLE_FIELDS)


@app.route("/stop", methods=["POST"])
def stop_scrape():
    with _lock:
        if not _state["running"]:
            return jsonify({"status": "not running"}), 200
        event = _state.get("stop_event")
        if event:
            event.set()
        return jsonify({"status": "stopping"}), 200


@app.route("/scrape", methods=["POST"])
def start_scrape():
    with _lock:
        if _state["running"]:
            return jsonify({"error": "A scrape is already running"}), 409

    data = request.get_json(force=True, silent=True) or {}
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query required"}), 400

    def as_bool(v):
        if isinstance(v, bool):
            return v
        return str(v).lower() in {"true", "1", "yes", "on"}

    raw_fields = data.get("fields")
    fields = None
    if isinstance(raw_fields, list) and raw_fields:
        fields = [str(f).strip() for f in raw_fields if str(f).strip()]

    config = Config(
        query=query,
        territory=data.get("territory", "Cambodia").strip(),
        headless=as_bool(data.get("headless", True)),
        log_level=data.get("log_level", "INFO").upper(),
        output_format=data.get("format", "csv").lower(),
        max_results=int(data.get("max_results", 0) or 0),
        concurrency=min(int(data.get("concurrency", 4) or 4), 8),
        proxy=data.get("proxy", "").strip(),
        screenshots=as_bool(data.get("screenshots", False)),
        fields=fields,
    )

    threading.Thread(target=lambda: asyncio.run(_worker(config)), daemon=True).start()
    return jsonify({"status": "started", "query": query})


@app.route("/status")
def status():
    with _lock:
        payload = dict(_state)
        # stop_event is an asyncio.Event and not JSON serializable
        payload.pop("stop_event", None)
        if payload.get("config"):
            payload["config"] = asdict(payload["config"])
        payload["logs"] = _logs[-250:]
        return jsonify(payload)


@app.route("/results")
def results():
    files = []
    if DATA_DIR.exists():
        for f in sorted(DATA_DIR.iterdir(), key=os.path.getmtime, reverse=True):
            if f.is_file() and f.suffix.lower() in {".csv", ".json", ".md", ".xlsx"}:
                files.append(
                    {
                        "name": f.name,
                        "type": f.suffix.lower().lstrip("."),
                        "size": f.stat().st_size,
                        "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    }
                )
    return jsonify({"files": files})


@app.route("/places-data")
def places_data():
    with _lock:
        places = _state.get("places_data", [])
    if not places:
        latest = sorted(DATA_DIR.glob("*.json"), key=os.path.getmtime, reverse=True)
        if latest:
            with contextlib.suppress(Exception):
                data = json.loads(latest[0].read_text(encoding="utf-8"))
                places = data.get("places", [])
    # Fallback: extract lat/lng from maps_url if missing
    for p in places:
        if not p.get("latitude") or not p.get("longitude"):
            url = p.get("maps_url") or p.get("url") or ""
            if m := (re.search(r"/@(-?\d+\.\d+),(-?\d+\.\d+)", url) or re.search(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)", url)):
                p["latitude"], p["longitude"] = m.group(1), m.group(2)
    return jsonify({"places": places})


@app.route("/download/<path:filename>")
def download(filename):
    return send_from_directory(DATA_DIR, os.path.basename(filename), as_attachment=True)


def run_web(host: str = "127.0.0.1", port: int = 5000):
    app.run(host=host, port=port, threaded=True)


if __name__ == "__main__":
    run_web()
