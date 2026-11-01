// ==UserScript==
// @name         Rota updater from AtoZ
// @namespace    local.rota-updater
// @version      4.2.0
// @description  Fill IN/OFF from schedules and HOL/SICK from approved AtoZ time off.
// @match        https://docs.google.com/spreadsheets/d/*
// @match        https://atoz.amazon.work/timecard/managerView/employeeDetails/*
// @grant        GM_xmlhttpRequest
// @grant        GM_openInTab
// @grant        GM_setValue
// @grant        GM_getValue
// @grant        GM_deleteValue
// @grant        GM_listValues
// @connect      script.google.com
// @connect      script.googleusercontent.com
// @run-at       document-idle
// @noframes
// ==/UserScript==

(() => {
    'use strict';
    const CONFIG = {
        helperUrl: 'https://script.google.com/macros/s/AKfycbzv9E3bNZZTaPBNukAekECToQotdVsCl9UCsVgfe041TZEhchaXTiqyN2rYz8nNB5G2/exec',
        token: '9f73c2a8e641b0d5a29c8f047e36d1b6c850af9327de6410b5a28c7f03e96d14',
        timezone: 'Europe/London',
    };
    const HOLIDAY_TYPES = new Set([
        'TimeOff_GBR_AnnualLeave_Days', 'TimeOff_GBR_AnnualLeave_Hours',
        'TimeOff_GBR_BankHoliday', 'TimeOff_GBR_Vacation',
    ]);
    function isSicknessType(type) {
        // Explicit sickness names only; do not infer sickness from punches or anomalies.
        const name = type.trim().toLowerCase().replace(/[\s_-]+/g, '').replace(/^timeoffgbr/, '');
        return /^(sick|sickness|sickleave|sicknessabsence)(days|hours)?$/.test(name);
    }
    const stopError = () => Object.assign(new Error('Stopped by user. Previously saved changes remain; unsent changes were discarded.'), { name: 'RotaStopped' });
    function checkStopped(run) { if (run?.stopped) throw stopError(); }
    function jsonRequest(url, body, run) {
        checkStopped(run);
        return new Promise((resolve, reject) => {
            const request = GM_xmlhttpRequest({
            method: 'POST', url, anonymous: false, timeout: 60000,
            headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
            data: JSON.stringify(body),
            onload(r) {
                if (r.status < 200 || r.status >= 300) return reject(new Error(`HTTP ${r.status}; check sign-in and permissions.`));
                try { resolve(JSON.parse(r.responseText)); }
                catch { reject(new Error('Expected JSON; open AtoZ and the helper URL to sign in/authorize.')); }
            },
            ontimeout: () => reject(new Error('Request timed out. A sheet write may have completed; inspect the rota before rerunning.')),
            onerror: () => reject(new Error('Network request failed. Check sign-in and Tampermonkey domain permissions.')),
            });
            if (run) run.cancel = () => { reject(stopError()); request.abort(); };
        }).finally(() => { if (run) run.cancel = null; });
    }
    function analyze(response, employeeId) {
        let data = response;
        if (data && Object.hasOwn(data, 'response')) data = data.response;
        if (typeof data === 'string') data = JSON.parse(data);
        if (!data || !Array.isArray(data.timeCardDayList)) throw new Error('Unrecognized holiday response: expected timeCardDayList.');
        if (data.errorMap && Object.keys(data.errorMap).length) throw new Error('AtoZ reported component errors.');
        const result = new Map();
        for (const day of data.timeCardDayList || []) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(day.date)) throw new Error('Unrecognized timecard date.');
            if (day.timeOff != null && !Array.isArray(day.timeOff)) throw new Error('Unrecognized timeOff collection.');
            for (const entry of day.timeOff || []) {
                if (employeeId && entry.employeeId && String(entry.employeeId) !== employeeId) throw new Error('Response employee ID does not match request.');
                if (String(entry.status).trim().toLowerCase() !== 'approved') continue;
                if (typeof entry.timeOffType !== 'string' || !entry.timeOffType.trim()) throw new Error('Approved time off has no type.');
                if (HOLIDAY_TYPES.has(entry.timeOffType)) result.set(day.date, 'HOL');
                else if (isSicknessType(entry.timeOffType) && result.get(day.date) !== 'HOL') result.set(day.date, 'SICK');

            }

        }

        return result;
    }
    const JOB_PREFIX = 'rota-tab-job:';
    function scheduleCodes(response, employeeId) {
        let data = response?.response ?? response;
        if (typeof data === 'string') data = JSON.parse(data);
        if (!Array.isArray(data?.timeCardDayList) || (data.errorMap && Object.keys(data.errorMap).length)) throw new Error('Missing or failed schedule data.');
        const codes = new Map();
        for (const day of data.timeCardDayList) {
            if (!/^\d{4}-\d{2}-\d{2}$/.test(day.date) || !Array.isArray(day.shifts) || codes.has(day.date)) throw new Error('Invalid or duplicate schedule day.');
            for (const shift of day.shifts) {
                if (!shift || String(shift.employeeId) !== employeeId || typeof shift.isDeleted !== 'boolean') throw new Error('Invalid shift identity or deletion status.');
            }
            codes.set(day.date, day.shifts.some(s => !s.isDeleted) ? 'IN' : 'OFF');
        }
        return codes;
    }
    const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
    async function fetchInAssociateTab(employee, startDate, endDate, run) {
        checkStopped(run);
        const id = crypto.randomUUID();
        const key = JOB_PREFIX + id;
        const expires = Date.now() + 180000;
        GM_setValue(key, { employee, startDate, endDate, timezone: CONFIG.timezone, expires });
        let tab;
        try {
            tab = GM_openInTab(`https://atoz.amazon.work/timecard/managerView/employeeDetails/${encodeURIComponent(employee.userId)}#rotaJob=${id}`, { active: false, insert: true, setParent: true });
            if (run) run.cancel = () => {
                GM_deleteValue(key);
                GM_deleteValue(key + ':result');
                if (tab) tab.close();
            };
            while (Date.now() < expires) {
                checkStopped(run);
                const result = GM_getValue(key + ':result');
                if (result) {
                    if (!result.ok) throw new Error(result.error);
                    return new Map(result.codes);
                }
                if (tab && tab.closed) throw new Error('The associate tab was closed before its response arrived.');
                await pause(500);
            }
            throw new Error('AtoZ tab timed out. Finish signing in, then rerun from the rota.');
        } finally {
            if (run) run.cancel = null;
            GM_deleteValue(key);
            GM_deleteValue(key + ':result');
            if (tab) tab.close();
        }
    }
    async function runAssociateTab() {
        const id = new URLSearchParams(location.hash.slice(1)).get('rotaJob');
        if (!id || !/^[a-f0-9-]{36}$/.test(id)) return;
        const key = JOB_PREFIX + id;
        const job = GM_getValue(key);
        if (!job || job.expires < Date.now()) return;
        const note = document.createElement('div');
        note.style.cssText = 'position:fixed;top:12px;right:12px;z-index:2147483647;background:#fff;color:#111;border:2px solid #f90;padding:16px;max-width:380px;font:14px Arial';
        note.textContent = 'Rota updater: reading this associate’s timecard...';
        document.body.append(note);
        let result;
        try {
            const login = decodeURIComponent(location.pathname.split('/').filter(Boolean).at(-1));
            if (login !== job.employee.userId) throw new Error('Associate page login does not match the rota.');
            const payload = { concernedEmployeeId: job.employee.employeeId, concernedEmployeeTimezone: job.timezone,
                startDate: job.startDate, endDate: job.endDate,
                components: ['AGGREGATED_PAYCODES', 'TIMEAWAY', 'REPORTED_ACTIVITY', 'ANOMALIES'] };
            const controller = new AbortController();
            const timer = setTimeout(() => controller.abort(), 60000);
            try {
                const request = async components => {
                const response = await fetch('/apis/TimehubEverywhereMFE/service-api/TimeHubES/execute-timecard-operation/get-timecard-data', {
                    method: 'POST', credentials: 'include', mode: 'same-origin', signal: controller.signal,
                    headers: { Accept: 'application/json, text/plain, */*', 'Content-Type': 'application/json' },
                    referrer: location.origin + location.pathname,
                    body: JSON.stringify({ payload: JSON.stringify({ ...payload, components }), operationType: 'GET_TIMECARD_DATA', concernedEmployeeId: job.employee.employeeId }),
                });
                if (!response.ok) throw new Error(`AtoZ HTTP ${response.status}. Check that you can view this associate's timecard, then rerun.`);
                if (response.redirected || !(response.headers.get('content-type') || '').includes('json')) throw new Error('AtoZ requires sign-in. Finish signing in here, then rerun from the rota.');
                    return response.json();
                };
                const holidayResponse = await request(payload.components);
                const holidays = analyze(holidayResponse, job.employee.employeeId);
                let holidayData = holidayResponse.response ?? holidayResponse;
                if (typeof holidayData === 'string') holidayData = JSON.parse(holidayData);
                const holidayDates = new Set(holidayData.timeCardDayList.map(d => d.date));
                const codes = scheduleCodes(await request(['PUNCH', 'SCHEDULE']), job.employee.employeeId);
                // Missing days are unknown, never inferred as OFF or used to erase HOL.
                for (const date of codes.keys()) if (!holidayDates.has(date)) codes.delete(date);
                for (const [date, code] of holidays) codes.set(date, code);
                result = { ok: true, codes: [...codes] };
            } finally { clearTimeout(timer); }
            note.textContent = 'Timecard read. Returning to the rota...';
        } catch (error) {
            result = { ok: false, error: error.name === 'AbortError' ? 'AtoZ request timed out; rerun from the rota.' : error.message };
            note.textContent = result.error;
        }
        // Do not recreate storage after the originating tab has cancelled/expired the job.
        if (GM_getValue(key) && Date.now() < job.expires) GM_setValue(key + ':result', result);
    }
    // Exposed only to the local test harness, not to the page.
    if (typeof module !== 'undefined' && module.exports) { module.exports = { analyze, scheduleCodes, fetchInAssociateTab, runAssociateTab }; return; }
    // Remove abandoned short-lived jobs on the next script load.
    for (const key of GM_listValues()) {
        if (!key.startsWith(JOB_PREFIX) || key.endsWith(':result')) continue;
        if (GM_getValue(key)?.expires < Date.now()) { GM_deleteValue(key); GM_deleteValue(key + ':result'); }
    }
    if (location.hostname === 'atoz.amazon.work') { runAssociateTab().catch(() => {}); return; }
    if (document.getElementById('atoz-rota-update')) return;
    const box = document.createElement('div');
    box.style.cssText = 'position:fixed;right:20px;top:70px;z-index:2147483647;background:white;color:#111;border:1px solid #888;padding:12px;width:340px;font:13px Arial;box-shadow:0 2px 10px #888';
    const button = document.createElement('button');
    button.id = 'atoz-rota-update';
    button.textContent = 'Update rota from AtoZ';
    const stop = document.createElement('button');
    stop.textContent = 'Stop';
    stop.disabled = true;
    stop.style.marginLeft = '8px';
    let currentRun = null;
    const status = document.createElement('div');
    const start = document.createElement('input'), end = document.createElement('input');
    start.type = end.type = 'date';
    start.title = 'First rota date'; end.title = 'Last rota date';
    const today = new Date();
    today.setDate(today.getDate() - today.getDay());
    const localISO = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    start.value = localISO(today); today.setDate(today.getDate()+6); end.value = localISO(today);
    status.style.cssText = 'white-space:pre-wrap;max-height:280px;overflow:auto;margin-top:8px';
    box.append(start, document.createTextNode(' to '), end, button, stop, status); document.body.append(box);
    const log = message => { status.textContent += message + '\n'; status.scrollTop = status.scrollHeight; };
    stop.onclick = () => {
        if (!currentRun) return;
        currentRun.stopped = true;
        stop.disabled = true;
        log(currentRun.saving ? 'Stop requested. Waiting for this associate’s save to finish; no further associates will be processed.' : 'Stopping...');
        if (!currentRun.saving) currentRun.cancel?.();
    };
    button.onclick = async () => {
        if (currentRun) return;
        const run = currentRun = { stopped: false, saving: false, cancel: null };
        stop.disabled = false;
        start.disabled = end.disabled = true;
        button.disabled = true; status.textContent = '';
        try {
            if (!start.value || !end.value || start.value > end.value || (Date.parse(end.value)-Date.parse(start.value))/86400000 > 6) throw new Error('Select a date range of 1–7 days.');
            const startDate = start.value, endDate = end.value;
            if (!/^https:\/\/script\.google\.com\/macros\/s\/[^/]+\/exec$/.test(CONFIG.helperUrl) || CONFIG.token.startsWith('PASTE_')) throw new Error('Configure helperUrl and token first; see README.');
            const spreadsheetId = location.pathname.match(/\/spreadsheets\/d\/([^/]+)/)?.[1];
            const gid = new URLSearchParams(location.hash.slice(1)).get('gid') || new URLSearchParams(location.search).get('gid') || '0';
            const helper = async (action, extra = {}) => {
                checkStopped(run);
                const response = await jsonRequest(CONFIG.helperUrl, { token: CONFIG.token, spreadsheetId, gid, startDate, endDate, action, ...extra }, action === 'read' ? run : undefined);
                if (!response.ok) throw new Error(response.error || 'Sheet helper failed.');
                return response;
            };
            log('Reading active rota tab...');
            const snapshot = await helper('read');
            if (snapshot.version !== 4.1) throw new Error('Update Code.gs and deploy a new version of the helper first.');
            checkStopped(run);
            let totalUpdated = 0;
            let skippedAssociates = 0;
            for (let i = 0; i < snapshot.employees.length; i++) {
                checkStopped(run);
                const employee = snapshot.employees[i];
                const changes = [];
                log(`${i + 1}/${snapshot.employees.length}: ${employee.userId}`);
                log('Opening associate AtoZ tab; keep the rota tab open.');
                try {
                    const codes = await fetchInAssociateTab(employee, snapshot.dates[0], snapshot.dates.at(-1), run);
                    checkStopped(run);
                    for (const [date, from] of Object.entries(employee.cells)) {
                        const code = codes.get(date);
                        if (['IN', 'OFF', 'HOL', 'SICK'].includes(code) && code !== from) changes.push({ row: employee.row, employeeId: employee.employeeId, userId: employee.userId, date, from, code });
                    }
                } catch (error) {
                    checkStopped(run);
                    changes.length = 0;
                    skippedAssociates++;
                    log(`Skipped ${employee.userId}: ${error.message || String(error)}`);
                }
                checkStopped(run);
                if (changes.length) {
                    log(`Saving ${changes.length} changes for ${employee.userId}...`);
                    run.saving = true;
                    try {
                        const saved = await helper('apply', { changes });
                        totalUpdated += saved.updated;
                        log(`Verified ${saved.updated} changes; skipped ${saved.skipped} changed/formula cells.`);
                        for (const c of saved.changes) log(`${c.userId} | ${c.date} | ${c.from || '(blank)'} → ${c.code}`);
                    } finally { run.saving = false; }
                    checkStopped(run);
                }
                await new Promise(resolve => setTimeout(resolve, 500));
            }
            checkStopped(run);
            log(`Complete: ${totalUpdated} verified changes; ${skippedAssociates} associates skipped due to errors.`);
        } catch (error) { log(`Stopped: ${error.message}`); }
        finally {
            currentRun = null;
            stop.disabled = true;
            start.disabled = end.disabled = false;
            button.disabled = false;
        }
    };
})();
