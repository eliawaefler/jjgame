const $ = sel => document.querySelector(sel);
const state = { token:null, user_id:null, ws:null, scores:{}, you:null };

function uiLogin(show){ $('#loginCard').style.display = show ? '' : 'none'; }
function uiMenu(show){ $('#menuCard').style.display = show ? '' : 'none'; }
function uiGame(show){ $('#gameArea').style.display = show ? '' : 'none'; }
function setBadge(){ $('#userBadge').textContent = state.user_id ? `uid:${state.user_id.slice(0,6)}` : 'not logged in'; }
function setScore(){ const my = state.scores?.[state.you] ?? 0; $('#score').textContent = my; }
function logMsg(msg){ const el = $('#log'); const div = document.createElement('div'); div.textContent = msg; el.prepend(div); }
function dbg(obj){ $('#debug').textContent = JSON.stringify(obj,null,2); }

async function login(){
  const username = $('#username').value || 'guest';
  const res = await fetch('/login', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({username})});
  if(!res.ok){ alert('login failed'); return; }
  const j = await res.json(); state.token = j.token; state.user_id = j.user_id; setBadge(); uiLogin(false); uiMenu(true);
}

async function loadStats(){
  if(!state.user_id) return;
  const res = await fetch(`/stats?user_id=${encodeURIComponent(state.user_id)}`);
  if(res.ok){ const j = await res.json(); $('#stats').textContent = `Games:${j.games}  Wins:${j.wins}  Losses:${j.losses}  Draws:${j.draws}`; }
}

function wsURL(){
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  return `${proto}://${location.host}/ws`;
}

function bindGameButtons(){
  $('#opt1').onclick = ()=> choose($('#opt1').textContent);
  $('#opt2').onclick = ()=> choose($('#opt2').textContent);
  $('#btnAbort').onclick = ()=> state.ws?.readyState===1 && state.ws.send(JSON.stringify({type:'abort'}));
}

function choose(c){
  if(!state.ws || state.ws.readyState!==1) return;
  $('#opt1').disabled=true; $('#opt2').disabled=true;
  state.ws.send(JSON.stringify({type:'choose', choice: c}));
}

function connectWS(mode){
  if(!state.token){ alert('Login first'); return; }
  if(state.ws){ try{state.ws.close();}catch(e){} }

  state.ws = new WebSocket(wsURL());
  uiGame(true); $('#log').innerHTML=''; $('#situation').textContent='—'; $('#roomInfo').textContent='';

  state.ws.onopen = () => {
    state.ws.send(JSON.stringify({token:state.token, mode, username:'web'}));
    logMsg('WS connected');
  };
  state.ws.onmessage = ev => {
    const msg = JSON.parse(ev.data); dbg(msg);
    if(msg.type==='round'){
      state.you = msg.you; state.scores = msg.scores || {}; setScore();
      $('#situation').textContent = msg.situation;
      $('#opt1').textContent = msg.option1; $('#opt2').textContent = msg.option2;
      $('#opt1').disabled = false; $('#opt2').disabled = false;
      $('#roomInfo').textContent = `room:${msg.room_id}  round:${msg.round}`;
    } else if(msg.type==='resolve'){
      state.scores = msg.scores||{}; setScore();
      logMsg(`Resolve: ${String(msg.chooser).slice(0,6)} chose ${msg.choice} (delta ${msg.delta})`);
      $('#opt1').disabled = true; $('#opt2').disabled = true;
    } else if(msg.type==='game_over'){
      state.scores = msg.scores||{}; setScore();
      logMsg(`Game Over (${msg.reason})`);
      uiGame(false); uiMenu(true); loadStats();
    } else if(msg.type==='late'){
      logMsg('Too late, choice ignored');
    } else if(msg.type==='ping'){
      state.ws.send(JSON.stringify({type:'pong'}));
    } else if(msg.type==='error'){
      logMsg('Error: '+msg.error);
    }
  };
  state.ws.onclose = () => { logMsg('WS closed'); };
  state.ws.onerror = (e) => { logMsg('WS error'); dbg(e); };
}

$('#btnLogin').onclick = login;
$('#btnLogout').onclick = ()=>{ if(state.ws) try{state.ws.close();}catch(e){} state.token=null; state.user_id=null; setBadge(); uiMenu(false); uiLogin(true); };
$('#btnStats').onclick = loadStats;
$('#btnSingle').onclick = ()=> connectWS('single');
$('#btnOnline').onclick = ()=> connectWS('online');
bindGameButtons();
