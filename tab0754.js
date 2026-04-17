// Tab0754 组件 — 独立JS文件，不经过Babel编译
// 注意：不使用任何展开运算符(...)，避免兼容问题
var STORAGE_0754 = '0754-sold-records';

function Tab0754() {
  var rS = React.useState(function() {
    try { return JSON.parse(localStorage.getItem(STORAGE_0754) || '[]'); }
    catch(e) { return []; }
  });
  var records = rS[0], setRecords = rS[1];
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

  async function loadFromExcel() {
    setLoading(true);
    setError(null);
    try {
      var resp = await fetch('./卡价.xlsx');
      if (!resp.ok) throw new Error('ERR');
      var buf = await resp.arrayBuffer();
      var wb = XLSX.read(new Uint8Array(buf), {type: 'array'});
      var sn = wb.SheetNames.find(function(n) { return n.includes('754'); }) || '754售出';
      var ws = wb.Sheets[sn];
      if (!ws) throw new Error('NO_SHEET');
      var vals = [];
      for (var r = 2; r <= 23; r++) {
        var c = ws['B' + (r + 1)];
        if (c && typeof c.v === 'number') vals.push(c.v);
      }
      var today = new Date().toISOString().slice(0, 10);
      saveRecords(vals.map(function(v, i) {
        return { id: i, date: today, amount: v, createdAt: new Date().toISOString() };
      }));
    } catch(e) {
      setError(String(e.message));
    }
    setLoading(false);
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
    C('select', P({value:sortField+'|'+sortDir, onChange:function(e) {
      var p = e.target.value.split('|'); setSortField(p[0]); setSortDir(p[1]);
    }}, S('style', {marginLeft:8,padding:'6px 10px',borderRadius:6,
      border:'1px solid rgba(48,54,61,0.8)',background:'#161b22',color:'#8b949e',
      fontSize:11,fontWeight:600,cursor:'pointer',outline:'none'})),
      C('option', {value:'date|desc'}, '\u6700\u65B0\u4F18\u5148'),
      C('option', {value:'date|asc'}, '\u6700\u65E7\u4F18\u5148'),
      C('option', {value:'amount|desc'}, '\u91D1\u989D \u9AD8\u2192\u4F4E'),
      C('option', {value:'amount|asc'}, '\u91D1\u989D \u4F4E\u2192\u9AD8')
    ),
    C('span', S('style', {fontSize:11,color:'#6e7681',marginLeft:'auto'}),
      '\u5171 ', C('strong', S('style',{color:'#e6edf3'}), records.length), ' \u7B14')
  );

  // 录入区
  var inputArea = C('div', S('style', {background:'rgba(22,27,34,0.85)',borderRadius:10,
    border:'1px solid rgba(48,54,61,0.8)',padding:'16px 20px',display:'flex',gap:10,
    alignItems:'center',marginBottom:24}),
    C('span', S('style', {fontSize:13,fontWeight:600,whiteSpace:'nowrap',color:'#8b949e'}), '+ \u65B0\u589E'),
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
        (dateFrom||dateTo) ? C('span', S('style',{color:'#58a6ff',marginLeft:4}), '(筛选)') : null),
      C('div', {className:'stat-value green'}, sf.length),
      C('div', {className:'stat-sub'}, '\u5171 ' + records.length + ' \u7B14\u8BB0\u5F55')
    ),
    C('div', {className:'stat-card green'},
      C('div', {className:'stat-label'},
        '\u552E\u51FA\u603B\u989D',
        (dateFrom||dateTo) ? C('span', S('style',{color:'#3fb950',marginLeft:4}), '(筛选)') : null),
      C('div', {className:'stat-value green'}, fmtY(dSum)),
      C('div', {className:'stat-sub'}, '\u603B\u8BA1 ' + fmtY(tSum))
    ),
    C('div', {className:'stat-card blue'},
      C('div', {className:'stat-label'},
        '\u5E73\u5747\u5355\u4EF7',
        (dateFrom||dateTo) ? C('span', S('style',{color:'#58a6ff',marginLeft:4}), '(筛选)') : null),
      C('div', {className:'stat-value'}, fmtY(dAvg)),
      C('div', {className:'stat-sub'}, '\u5747\u503C ' + fmtY(tSum / (records.length || 1)))
    )
  );

  // 日期筛选栏
  var dateFilterBorder = (dateFrom||dateTo) ? '1px solid #58a6ff' : '1px solid rgba(48,54,61,0.8)';
  var fromDateBorder = dateFrom ? '#58a6ff' : 'rgba(48,54,61,0.8)';
  var toDateBorder = dateTo ? '#58a6ff' : 'rgba(48,54,61,0.8)';
  var clearBtnOrHint;
  if (dateFrom || dateTo) {
    clearBtnOrHint = C('button',
      P({onClick:function(){setDateFrom('');setDateTo('');}},
        S('style', {marginLeft:'auto', background:'none', border:'1px solid rgba(248,81,73,0.3)',
          color:'#f85149', fontSize:11, padding:'4px 10px', borderRadius:6,
          cursor:'pointer', fontWeight:600})),
      ' \u2715 \u6E05\u9664'
    );
  } else {
    clearBtnOrHint = C('span', S('style', {marginLeft:'auto', fontSize:11, color:'#6e7681'}),
      ' \u9009\u62E9\u8D77\u6B62\u65E5\u671F\u53EF\u7B5F\u9009');
  }

  var dateFilter = C('div', S('style', {
    background:'rgba(22,27,34,0.85)', borderRadius:10, border:dateFilterBorder,
    padding:'12px 20px', display:'flex', gap:16, alignItems:'center', marginBottom:24, flexWrap:'wrap'}),
    C('span', S('style', {fontSize:13,fontWeight:600,whiteSpace:'nowrap',color:'#8b949e'}), ' \u7B5F\u9009\u65E5\u671F'),
    C('span', S('style', {fontSize:11,color:'#6e7681'}), '\u4ECE'),
    C('input', P({type:'date', value:dateFrom, onChange:function(e){setDateFrom(e.target.value)}},
      S('style', {background:'#0d1117', border:'1px solid '+fromDateBorder, borderRadius:6,
        color:'#e6edf3', fontSize:12, padding:'5px 10px'}))),
    C('span', S('style', {fontSize:11,color:'#6e7681'}), '\u5230'),
    C('input', P({type:'date', value:dateTo, onChange:function(e){setDateTo(e.target.value)}},
      S('style', {background:'#0d1117', border:'1px solid '+toDateBorder, borderRadius:6,
        color:'#e6edf3', fontSize:12, padding:'5px 10px'}))),
    clearBtnOrHint
  );

  // 表格内容
  var tableContent;
  if (sf.length === 0 && records.length > 0) {
    tableContent = C('div', S('style', {padding:'40px 20px', textAlign:'center', color:'#6e7681', fontSize:13}), '\u8BE5\u65F6\u95F4\u6BB5\u65E0\u8BB0\u5F55');
  } else if (records.length === 0) {
    tableContent = C('div', S('style', {padding:'40px 20px', textAlign:'center', color:'#6e7681', fontSize:13}),
      '\u6682\u65E0\u8BB0\u5F55\uFF0C\u8BF7\u4ECEExcel\u5BFC\u5165');
  } else {
    var thRows = [];
    thRows.push(C('th', S('style', {padding:'10px 20px',textAlign:'left',fontSize:11,color:'#6e7681',fontWeight:500}), '#'));
    var dateColor = sortField==='date'?'#58a6ff':'#6e7681';
    var dateArrow = sortField==='date'?(sortDir==='asc'?'\u2191':'\u2193'):'\u21C5';
    thRows.push(C('th', P({onClick:function(){hSort('date');}},
      S('style', {padding:'10px 20px',textAlign:'left',fontSize:11,fontWeight:500,cursor:'pointer',
        userSelect:'none', color:dateColor})), '\u65E5\u671F ' + dateArrow));
    var amtColor = sortField==='amount'?'#58a6ff':'#6e7681';
    var amtArrow = sortField==='amount'?(sortDir==='asc'?'\u2191':'\u2193'):'\u21C5';
    thRows.push(C('th', P({onClick:function(){hSort('amount');}},
      S('style', {padding:'10px 20px',textAlign:'right',fontSize:11,fontWeight:500,cursor:'pointer',
        userSelect:'none', color:amtColor})),
      '\u5355\u4EF7 (\u00A5) ' + amtArrow));
    thRows.push(C('th', S('style', {padding:'10px 20px',textAlign:'right',fontSize:11,color:'#6e7681',fontWeight:500}), '\u7D2F\u8BA1 (\u00A5)'));
    thRows.push(C('th', S('style', {padding:'10px 20px',textAlign:'center',fontSize:11,color:'#6e7681',fontWeight:500}), '\u64CD\u4F5C'));

    var bodyRows = [];
    for (var idx = 0; idx < sf.length; idx++) {
      var rec = sf[idx];
      var cumsum = sf.slice(0, idx+1).reduce(function(a,b){return a+b.amount;},0);
      var rowBg = (idx>0&&sf[idx].date!==sf[idx-1].date)?'rgba(88,166,255,0.06)':'none';
      bodyRows.push(
        C('tr', P({key:rec.id}, S('style', {borderTop:idx>0?'1px solid rgba(48,54,61,0.4)':'none'})),
          C('td', S('style', {padding:'10px 20px',fontSize:13,color:'#8b949e'}), idx+1),
          C('td', S('style', {padding:'10px 20px',fontSize:13,fontVariantNumeric:'tabular-nums',background:rowBg}), fmtD(rec.date)),
          C('td', S('style', {padding:'10px 20px',textAlign:'right',fontSize:14,fontWeight:600,fontVariantNumeric:'tabular-nums',color:'#3fb950'}), fmtY(rec.amount)),
          C('td', S('style', {padding:'10px 20px',textAlign:'right',fontSize:13,fontVariantNumeric:'tabular-nums',color:'#8b949e'}), fmtY(cumsum)),
          C('td', S('style', {padding:'10px 20px',textAlign:'center'}),
            C('button', P({onClick:function(){delRec(rec.id);}},
              S('style', {color:'#f85149',cursor:'pointer',background:'none',border:'none',
                fontSize:18,padding:'2px 6px',borderRadius:4,title:'\u5220\u9664'})), '\u2715'))
        )
      );
    }

    var filterNote = (dateFrom||dateTo) ? C('span', S('style',{color:'#58a6ff',fontSize:10,marginLeft:6}),'(筛选)') : null;

    bodyRows.push(
      C('tr', S('style', {borderTop:'1px solid rgba(48,54,61,0.8)',background:'rgba(33,38,45,0.5)'}),
        C('td', P({colSpan:2}, S('style',{padding:'12px 20px',fontWeight:700,color:'#8b949e'})),
          '\u5408\u8BA1', filterNote),
        C('td', S('style', {padding:'12px 20px',textAlign:'right',fontWeight:700,fontSize:15,color:'#3fb950'}), fmtY(dSum)),
        C('td', S('style', {padding:'12px 20px'})), C('td', null))
    );

    tableContent = C('table', S('style', {width:'100%', borderCollapse:'collapse'}),
      C('thead', null, C('tr', S('style', {background:'rgba(33,38,45,0.5)'}), thRows)),
      C('tbody', null, bodyRows)
    );
  }

  var tableArea = C('div', S('style', {background:'rgba(22,27,34,0.85)',borderRadius:10,
    border:'1px solid rgba(48,54,61,0.8)',overflow:'hidden'}),
    C('div', S('style', {padding:'14px 20px',background:'rgba(33,38,45,0.8)',
      borderBottom:'1px solid rgba(48,54,61,0.8)',fontSize:12,fontWeight:600,color:'#8b949e'}), '\u552E\u51FA\u660E\u7EC6'),
    tableContent
  );

  var errorEl = error ? C('div', S('style', {
    background:'rgba(248,81,73,0.1)', border:'1px solid rgba(248,81,73,0.3)',
    borderRadius:10, padding:'16px 20px', color:'#f85149', marginTop:16}), ' ', error) : null;

  return C('div', S('style', {maxWidth:1400, margin:'0 auto', padding:'24px 32px 48px'}),
    titleBar, inputArea, statsArea, dateFilter, tableArea, errorEl
  );
}
