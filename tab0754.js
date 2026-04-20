// Tab0754 组件 — 独立JS文件，不经过Babel编译
// 注意：不使用任何展开运算符(...)，避免兼容问题
var STORAGE_0754 = '0754-sold-records';

function Tab0754() {
  var rS = React.useState(function() {
    try { return JSON.parse(localStorage.getItem(STORAGE_0754) || '[]'); }
    catch(e) { return []; }
  });
  var records = rS[0], setRecords = rS[1];
  var fileInputRef = React.useRef(null);
  var iaS = React.useState('');
  var inputAmount = iaS[0], setInputAmount = iaS[1];
  var ldS = React.useState(false);
  var loading = ldS[0], setLoading = ldS[1];
  var erS = React.useState(null);
  var error = erS[0], setError = erS[1];
  var sfS = React.useState('date');
  var sortField = sfS[0], setSortField = sfS[1];
  var sdS = React.useState('desc');
  var sortDir = sdS[0], setSortDir = sdS[1];
  var dfS = React.useState('');
  var dateFrom = dfS[0], setDateFrom = dfS[1];
  var dtS = React.useState('');
  var dateTo = dtS[0], setDateTo = dtS[1];

  function saveRecords(data) {
    localStorage.setItem(STORAGE_0754, JSON.stringify(data));
    setRecords(data);
  }

  function parseAmountCell(value) {
    if (typeof value === 'number') return value;
    if (typeof value === 'string') {
      var cleaned = value.replace(/[,\s¥￥]/g, '');
      var parsed = parseFloat(cleaned);
      if (!isNaN(parsed)) return parsed;
    }
    return null;
  }

  function getTodayString() {
    return new Date().toLocaleDateString('en-CA');
  }

  function parseExcelBuffer(buf) {
    if (!window.XLSX) throw new Error('Excel 解析库未加载，请刷新页面后重试');
    var wb = XLSX.read(new Uint8Array(buf), {type: 'array'});
    var sn = wb.SheetNames.find(function(n) { return String(n).includes('0754') || String(n).includes('754'); })
      || wb.SheetNames.find(function(n) { return String(n).includes('售出'); })
      || wb.SheetNames[0];
    var ws = wb.Sheets[sn];
    if (!ws) throw new Error('Excel 中没有可读取的工作表');

    var vals = [];
    for (var row = 3; row <= 24; row++) {
      var cell = ws['B' + row];
      var amount = cell ? parseAmountCell(cell.v) : null;
      if (amount !== null) vals.push(amount);
    }

    if (vals.length === 0) {
      throw new Error('没有在工作表 B3:B24 里读到金额，请检查 Excel 内容');
    }

    var today = getTodayString();
    return vals.map(function(v, i) {
      return { id: Date.now() + i, date: today, amount: v, createdAt: new Date().toISOString() };
    });
  }

  async function importExcelFromBuffer(buf) {
    var parsed = parseExcelBuffer(buf);
    saveRecords(parsed);
    setError(null);
  }

  async function loadBundledExcel() {
    var resp = await fetch('./卡价.xlsx');
    if (!resp.ok) {
      throw new Error(resp.status === 404
        ? '未找到线上 Excel 文件，已为你切换到本地选文件导入'
        : '读取 Excel 失败（HTTP ' + resp.status + '）');
    }
    var buf = await resp.arrayBuffer();
    await importExcelFromBuffer(buf);
  }

  async function loadFromExcel() {
    setLoading(true);
    setError(null);
    try {
      await loadBundledExcel();
    } catch(e) {
      var msg = String(e && e.message ? e.message : e);
      if (msg.indexOf('未找到线上 Excel 文件') !== -1 && fileInputRef.current) {
        fileInputRef.current.value = '';
        fileInputRef.current.click();
      } else {
        setError(msg);
      }
    }
    setLoading(false);
  }

  function handleExcelFileChange(e) {
    var file = e.target.files && e.target.files[0];
    if (!file) return;

    setLoading(true);
    setError(null);

    file.arrayBuffer()
      .then(function(buf) {
        return importExcelFromBuffer(buf);
      })
      .catch(function(err) {
        setError(String(err && err.message ? err.message : err));
      })
      .finally(function() {
        setLoading(false);
        if (fileInputRef.current) fileInputRef.current.value = '';
      });
  }

  function addRecord() {
    var amt = parseFloat(inputAmount);
    if (!amt || amt <= 0) return;
    saveRecords(records.concat({
      id: Date.now(),
      date: new Date().toISOString().slice(0, 10),
      amount: amt,
      createdAt: new Date().toISOString()
    }));
    setInputAmount('');
  }

  function delRec(id) {
    saveRecords(records.filter(function(r) { return r.id !== id; }));
  }

  function fmtY(v) { return '\u00A5' + Number(v || 0).toFixed(2); }
  function fmtD(d) { return String(d || '--------').slice(5); }
  function S(k, v) { var o = {}; o[k] = v; return o; }

  // 合并props的工具函数（替代...展开运算符）
  function P(/* ...args */) {
    var result = {};
    for (var i = 0; i < arguments.length; i++) {
      var arg = arguments[i];
      if (arg) {
        var keys = Object.keys(arg);
        for (var j = 0; j < keys.length; j++) {
          result[keys[j]] = arg[keys[j]];
        }
      }
    }
    return result;
  }

  function getSF() {
    var list = records.slice().sort(function(a, b) {
      var av = sortField === 'date' ? (a.date || '') : (a[sortField] || '');
      var bv = sortField === 'date' ? (b.date || '') : (b[sortField] || '');
      if (av < bv) return sortField === 'asc' ? -1 : 1;
      if (av > bv) return sortField === 'asc' ? 1 : -1;
      return 0;
    });
    if (dateFrom) list = list.filter(function(r) { return (r.date || '') >= dateFrom; });
    if (dateTo) list = list.filter(function(r) { return (r.date || '') <= dateTo; });
    return list;
  }

  var sf = getSF();
  var dSum = sf.reduce(function(a, b) { return a + (b.amount || 0); }, 0);
  var dAvg = sf.length > 0 ? dSum / sf.length : 0;
  var tSum = records.reduce(function(a, b) { return a + (b.amount || 0); }, 0);

  function hSort(fld) {
    if (sortField === fld) {
      setSortDir(function(d) { return d === 'asc' ? 'desc' : 'asc'; });
    } else {
      setSortField(fld);
      setSortDir('desc');
    }
  }

  var C = React.createElement;

  // ===== 构建各部分 =====

  // 标题栏
  var titleBar = C('div', S('style', {display:'flex',alignItems:'center',gap:12,marginBottom:20}),
    C('div', S('style', {fontSize:20,fontWeight:700}), '0754 \u552E\u51FA'),
    C('button', P({className:'btn btn-secondary', onClick:loadFromExcel, disabled:loading},
      S('style', {fontSize:12,padding:'4px 12px'})),
      loading ? '\u52A0\u8F7D\u4E2D...' : (records.length === 0 ? '\u4ECEExcel\u5BFC\u5165' : '\u4ECEExcel\u91CD\u7F6E')),
    C('input', {
      ref: fileInputRef,
      type: 'file',
      accept: '.xlsx,.xls',
      style: {display:'none'},
      onChange: handleExcelFileChange
    }),
    C('select', P({value:sortField+'|'+sortDir, onChange:function(e) {
      var p = e.target.value.split('|'); setSortField(p[0]); setSortDir(p[1]);
    }, className:'toolbar-select'}, S('style', {marginLeft:8})),
      C('option', {value:'date|desc'}, '\u6700\u65B0\u4F18\u5148'),
      C('option', {value:'date|asc'}, '\u6700\u65E7\u4F18\u5148'),
      C('option', {value:'amount|desc'}, '\u91D1\u989D \u9AD8\u2192\u4F4E'),
      C('option', {value:'amount|asc'}, '\u91D1\u989D \u4F4E\u2192\u9AD8')
    ),
    C('span', S('style', {fontSize:11,color:'var(--text-3)',marginLeft:'auto'}),
      '\u5171 ', C('strong', S('style',{color:'var(--text)'}), records.length), ' \u7B14')
  );

  // 录入区
  var inputArea = C('div', S('style', {background:'var(--surface-solid)',borderRadius:20,
    border:'1px solid var(--border)',padding:'20px 22px',display:'flex',gap:12,
    alignItems:'center',marginBottom:28, boxShadow:'0 18px 40px rgba(0,0,0,0.22)'}),
    C('span', S('style', {fontSize:13,fontWeight:600,whiteSpace:'nowrap',color:'var(--text-2)'}), '+ \u65B0\u589E'),
    C('input', P({className:'form-input',type:'number',step:'0.01',value:inputAmount,
      onChange:function(e){setInputAmount(e.target.value)},placeholder:'\u91D1\u989D',
      onKeyDown:function(e){if(e.key==='Enter')addRecord();}},
      S('style',{width:140,fontSize:14}))),
    C('button', P({className:'btn btn-primary',onClick:addRecord,disabled:!inputAmount},
      S('style',{padding:'6px 16px',fontSize:13})), '\u6DFB\u52A0')
  );

  // 统计卡
  var statsArea = C('div', S('style', {display:'grid',gridTemplateColumns:'repeat(3,1fr)',gap:16,marginBottom:24}),
    C('div', {className:'stat-card green'},
      C('div', {className:'stat-label'},
        '\u552E\u51FA\u7B14\u6570',
        (dateFrom||dateTo) ? C('span', S('style',{color:'var(--primary)',marginLeft:4}), '(筛选)') : null),
      C('div', {className:'stat-value green'}, sf.length),
      C('div', {className:'stat-sub'}, '\u5171 ' + records.length + ' \u7B14\u8BB0\u5F55')
    ),
    C('div', {className:'stat-card green'},
      C('div', {className:'stat-label'},
        '\u552E\u51FA\u603B\u989D',
        (dateFrom||dateTo) ? C('span', S('style',{color:'var(--green)',marginLeft:4}), '(筛选)') : null),
      C('div', {className:'stat-value green'}, fmtY(dSum)),
      C('div', {className:'stat-sub'}, '\u603B\u8BA1 ' + fmtY(tSum))
    ),
    C('div', {className:'stat-card blue'},
      C('div', {className:'stat-label'},
        '\u5E73\u5747\u5355\u4EF7',
        (dateFrom||dateTo) ? C('span', S('style',{color:'var(--primary)',marginLeft:4}), '(筛选)') : null),
      C('div', {className:'stat-value'}, fmtY(dAvg)),
      C('div', {className:'stat-sub'}, '\u5747\u503C ' + fmtY(tSum / (records.length || 1)))
    )
  );

  // 日期筛选栏
  var dateFilterBorder = (dateFrom||dateTo) ? '1px solid rgba(62,207,142,0.32)' : '1px solid var(--border)';
  var fromDateBorder = dateFrom ? 'rgba(62,207,142,0.38)' : 'var(--border)';
  var toDateBorder = dateTo ? 'rgba(62,207,142,0.38)' : 'var(--border)';
  var clearBtnOrHint;
  if (dateFrom || dateTo) {
    clearBtnOrHint = C('button',
      P({onClick:function(){setDateFrom('');setDateTo('');}},
        S('style', {marginLeft:'auto', background:'var(--red-bg)', border:'1px solid var(--red-border)',
          color:'var(--red)', fontSize:11, padding:'6px 10px', borderRadius:999,
          cursor:'pointer', fontWeight:600})),
      ' \u2715 \u6E05\u9664'
    );
  } else {
    clearBtnOrHint = C('span', S('style', {marginLeft:'auto', fontSize:11, color:'var(--text-3)'}),
      ' \u9009\u62E9\u8D77\u6B62\u65E5\u671F\u53EF\u7B5F\u9009');
  }

  var dateFilter = C('div', S('style', {
    background:'var(--surface-solid)', borderRadius:20, border:dateFilterBorder,
    padding:'16px 22px', display:'flex', gap:16, alignItems:'center', marginBottom:28, flexWrap:'wrap',
    boxShadow:'0 18px 40px rgba(0,0,0,0.22)'}),
    C('span', S('style', {fontSize:13,fontWeight:600,whiteSpace:'nowrap',color:'var(--text-2)'}), ' \u7B5F\u9009\u65E5\u671F'),
    C('span', S('style', {fontSize:11,color:'var(--text-3)'}), '\u4ECE'),
    C('input', P({type:'date', value:dateFrom, onChange:function(e){setDateFrom(e.target.value)}},
      S('style', {background:'var(--surface-3)', border:'1px solid '+fromDateBorder, borderRadius:8,
        color:'var(--text)', fontSize:12, padding:'8px 10px'}))),
    C('span', S('style', {fontSize:11,color:'var(--text-3)'}), '\u5230'),
    C('input', P({type:'date', value:dateTo, onChange:function(e){setDateTo(e.target.value)}},
      S('style', {background:'var(--surface-3)', border:'1px solid '+toDateBorder, borderRadius:8,
        color:'var(--text)', fontSize:12, padding:'8px 10px'}))),
    clearBtnOrHint
  );

  // 表格内容
  var tableContent;
  if (sf.length === 0 && records.length > 0) {
    tableContent = C('div', S('style', {padding:'40px 20px', textAlign:'center', color:'var(--text-3)', fontSize:13}), '\u8BE5\u65F6\u95F4\u6BB5\u65E0\u8BB0\u5F55');
  } else if (records.length === 0) {
    tableContent = C('div', S('style', {padding:'40px 20px', textAlign:'center', color:'var(--text-3)', fontSize:13}),
      '\u6682\u65E0\u8BB0\u5F55\uFF0C\u8BF7\u4ECEExcel\u5BFC\u5165');
  } else {
    var thRows = [];
    thRows.push(C('th', S('style', {padding:'10px 20px',textAlign:'left',fontSize:11,color:'var(--text-3)',fontWeight:500}), '#'));
    var dateColor = sortField==='date'?'var(--primary)':'var(--text-3)';
    var dateArrow = sortField==='date'?(sortDir==='asc'?'\u2191':'\u2193'):'\u21C5';
    thRows.push(C('th', P({onClick:function(){hSort('date');}},
      S('style', {padding:'10px 20px',textAlign:'left',fontSize:11,fontWeight:500,cursor:'pointer',
        userSelect:'none', color:dateColor})), '\u65E5\u671F ' + dateArrow));
    var amtColor = sortField==='amount'?'var(--primary)':'var(--text-3)';
    var amtArrow = sortField==='amount'?(sortDir==='asc'?'\u2191':'\u2193'):'\u21C5';
    thRows.push(C('th', P({onClick:function(){hSort('amount');}},
      S('style', {padding:'10px 20px',textAlign:'right',fontSize:11,fontWeight:500,cursor:'pointer',
        userSelect:'none', color:amtColor})),
      '\u5355\u4EF7 (\u00A5) ' + amtArrow));
    thRows.push(C('th', S('style', {padding:'10px 20px',textAlign:'right',fontSize:11,color:'var(--text-3)',fontWeight:500}), '\u7D2F\u8BA1 (\u00A5)'));
    thRows.push(C('th', S('style', {padding:'10px 20px',textAlign:'center',fontSize:11,color:'var(--text-3)',fontWeight:500}), '\u64CD\u4F5C'));

    var bodyRows = [];
    for (var idx = 0; idx < sf.length; idx++) {
      var rec = sf[idx];
      var cumsum = sf.slice(0, idx+1).reduce(function(a,b){return a+b.amount;},0);
      var rowBg = (idx>0&&sf[idx].date!==sf[idx-1].date)?'rgba(62,207,142,0.05)':'none';
      bodyRows.push(
        C('tr', P({key:rec.id}, S('style', {borderTop:idx>0?'1px solid rgba(255,255,255,0.06)':'none'})),
          C('td', S('style', {padding:'10px 20px',fontSize:13,color:'var(--text-2)'}), idx+1),
          C('td', S('style', {padding:'10px 20px',fontSize:13,fontVariantNumeric:'tabular-nums',background:rowBg}), fmtD(rec.date)),
          C('td', S('style', {padding:'10px 20px',textAlign:'right',fontSize:14,fontWeight:600,fontVariantNumeric:'tabular-nums',color:'var(--green)'}), fmtY(rec.amount)),
          C('td', S('style', {padding:'10px 20px',textAlign:'right',fontSize:13,fontVariantNumeric:'tabular-nums',color:'var(--text-2)'}), fmtY(cumsum)),
          C('td', S('style', {padding:'10px 20px',textAlign:'center'}),
            C('button', P({onClick:function(){delRec(rec.id);}},
              S('style', {color:'var(--red)',cursor:'pointer',background:'none',border:'none',
                fontSize:18,padding:'2px 6px',borderRadius:4,title:'\u5220\u9664'})), '\u2715'))
        )
      );
    }

    var filterNote = (dateFrom||dateTo) ? C('span', S('style',{color:'var(--primary)',fontSize:10,marginLeft:6}),'(筛选)') : null;

    bodyRows.push(
      C('tr', S('style', {borderTop:'1px solid var(--border)',background:'rgba(17,17,17,0.96)'}),
        C('td', P({colSpan:2}, S('style',{padding:'12px 20px',fontWeight:700,color:'var(--text-2)'})),
          '\u5408\u8BA1', filterNote),
        C('td', S('style', {padding:'12px 20px',textAlign:'right',fontWeight:700,fontSize:15,color:'var(--green)'}), fmtY(dSum)),
        C('td', S('style', {padding:'12px 20px'})), C('td', null))
    );

    tableContent = C('table', S('style', {width:'100%', borderCollapse:'collapse'}),
      C('thead', null, C('tr', S('style', {background:'var(--surface-3)'}), thRows)),
      C('tbody', null, bodyRows)
    );
  }

  var tableArea = C('div', S('style', {background:'var(--surface-solid)',borderRadius:20,
    border:'1px solid var(--border)',overflow:'hidden', boxShadow:'0 18px 40px rgba(0,0,0,0.24)'}),
    C('div', S('style', {padding:'14px 20px',background:'var(--surface-3)',
      borderBottom:'1px solid var(--border)',fontSize:12,fontWeight:600,color:'var(--text-2)'}), '\u552E\u51FA\u660E\u7EC6'),
    tableContent
  );

  var errorEl = error ? C('div', S('style', {
    background:'var(--red-bg)', border:'1px solid var(--red-border)',
    borderRadius:16, padding:'16px 20px', color:'var(--red)', marginTop:16}),
    C('div', S('style', {fontWeight:700, marginBottom:6}), '导入失败'),
    C('div', null, error)
  ) : null;

  return C('div', S('style', {maxWidth:1400, margin:'0 auto', padding:'24px 32px 48px'}),
    titleBar, inputArea, statsArea, dateFilter, tableArea, errorEl
  );
}
