// Paste into Extensions > Apps Script for the rota spreadsheet.
const ROTA = {
  spreadsheetId: 'PASTE_SPREADSHEET_ID',
  headerRow: 1,
  dateRow: 3,
  dataStartRow: 5,
  employeeIdHeader: 'Employee ID',
  userIdHeader: 'User ID',
  timezone: 'Europe/London'
};

function doGet() { return ContentService.createTextOutput('Rota helper ready.'); }

function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    const input = JSON.parse(e.postData.contents);
    const token = PropertiesService.getScriptProperties().getProperty('ROTA_TOKEN');
    if (!token || token.length < 32 || input.token !== token) throw new Error('Invalid helper token.');
    if (input.spreadsheetId !== ROTA.spreadsheetId) throw new Error('Wrong spreadsheet.');
    lock.waitLock(30000);
    const book = SpreadsheetApp.openById(ROTA.spreadsheetId);
    const sheet = book.getSheets().find(s => String(s.getSheetId()) === String(input.gid));
    if (!sheet) throw new Error('Unknown sheet tab.');
    const values = sheet.getDataRange().getValues();
    const displayed = sheet.getDataRange().getDisplayValues();
    const headers = values[ROTA.headerRow - 1];
    const findHeader = name => {
      const matches = headers.map((v, i) => String(v).trim().toLowerCase() === name.toLowerCase() ? i : -1).filter(i => i >= 0);
      if (matches.length !== 1) throw new Error('Expected exactly one header: ' + name);
      return matches[0];
    };
    const employeeCol = findHeader(ROTA.employeeIdHeader), userCol = findHeader(ROTA.userIdHeader);
    const dateCols = {};
    values[ROTA.dateRow - 1].forEach((value, index) => {
      let date;
      if (value instanceof Date && !isNaN(value)) date = Utilities.formatDate(value, ROTA.timezone, 'yyyy-MM-dd');
      else {
        const text = String(value).trim();
        const match = text.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        date = match ? `${match[3]}-${match[2].padStart(2,'0')}-${match[1].padStart(2,'0')}` : /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : null;
      }
      if (!date) return;
      if (!/^\d{4}-\d{2}-\d{2}$/.test(input.startDate) || !/^\d{4}-\d{2}-\d{2}$/.test(input.endDate) || input.startDate > input.endDate) throw new Error('Invalid selected date range.');
      if (date < input.startDate || date > input.endDate) return;
      if (isNaN(Date.parse(date)) || new Date(date).toISOString().slice(0,10) !== date) throw new Error('Invalid date header.');
      if (dateCols[date] !== undefined) throw new Error('Duplicate date header.');
      dateCols[date] = index;
    });
    const dates = Object.keys(dateCols).sort();
    if (!dates.length) throw new Error('No full date headers found.');
    if ((Date.parse(dates[dates.length - 1]) - Date.parse(dates[0])) / 86400000 > 31) throw new Error('Use a rota tab spanning at most 32 days.');
    if (input.action === 'read') {
      const employees = [];
      for (let r = ROTA.dataStartRow - 1; r < values.length; r++) {
        const employeeId = displayed[r][employeeCol].trim(), userId = displayed[r][userCol].trim();
        if (!employeeId && !userId) continue;
        if (!/^\d{6,12}$/.test(employeeId) || !/^[a-zA-Z0-9._-]+$/.test(userId)) throw new Error('Missing/invalid employee identity on row ' + (r + 1));
        const cells = {};
        for (const d of dates) {
          const value = String(values[r][dateCols[d]]).trim();
          if (['', 'IN', 'OFF', 'HOL'].includes(value)) cells[d] = value;
        }
        if (Object.keys(cells).length) employees.push({ row: r + 1, employeeId, userId, cells });
      }
      return reply_({ ok: true, version: 4.1, dates, employees });
    }
    if (input.action !== 'apply' || !Array.isArray(input.changes)) throw new Error('Invalid action.');
    // Validate the entire request before writing anything.
    const seen = new Set();
    for (const c of input.changes) {
      if (!Number.isInteger(c.row) || c.row < ROTA.dataStartRow || c.row > values.length || dateCols[c.date] === undefined || !['IN','OFF','HOL','SICK'].includes(c.code) || !['','IN','OFF','HOL'].includes(c.from)) throw new Error('Invalid proposed cell.');
      if (displayed[c.row-1][employeeCol].trim() !== c.employeeId || displayed[c.row-1][userCol].trim() !== c.userId) throw new Error('Employee rows changed; run again.');
      const key = c.row + ':' + c.date;
      if (seen.has(key)) throw new Error('Duplicate proposed cell.');
      seen.add(key);
    }
    const changed = [];
    let skipped = 0;
    for (const c of input.changes) {
      const cell = sheet.getRange(c.row, dateCols[c.date] + 1);
      if (cell.getFormula() || String(cell.getValue()).trim() !== c.from) { skipped++; continue; }
      // Recheck identity immediately before each write.
      if (sheet.getRange(c.row, employeeCol+1).getDisplayValue().trim() !== c.employeeId || sheet.getRange(c.row, userCol+1).getDisplayValue().trim() !== c.userId) throw new Error('Rows moved during update; inspect rota before rerunning.');
      cell.setValue(c.code);
      changed.push(c);
    }
    SpreadsheetApp.flush();
    for (const c of changed) if (sheet.getRange(c.row,dateCols[c.date]+1).getValue() !== c.code) throw new Error('Write verification failed; inspect rota.');
    return reply_({ ok: true, updated: changed.length, skipped, changes: changed });
  } catch (error) {
    return reply_({ ok: false, error: error.message + ' If saving had started, some cells may already be updated.' });
  } finally { if (lock.hasLock()) lock.releaseLock(); }
}
function reply_(data) { return ContentService.createTextOutput(JSON.stringify(data)).setMimeType(ContentService.MimeType.JSON); }
