from __future__ import annotations

from fastapi.responses import HTMLResponse


HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Digital Human SaaS Studio</title>
<style>
:root{--bg:#080b12;--panel:#111722;--panel2:#161e2b;--line:#263247;--text:#ecf2ff;--muted:#91a0b7;--brand:#4f8cff;--bad:#ff667a;--shadow:0 18px 60px #0007}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC",sans-serif}button,input,select,textarea{font:inherit}.hidden{display:none!important}.auth{min-height:100vh;display:grid;place-items:center;padding:24px}.auth-card{width:min(920px,100%);display:grid;grid-template-columns:1fr 1fr;background:#0d121c;border:1px solid var(--line);border-radius:22px;overflow:hidden;box-shadow:var(--shadow)}.hero{padding:52px;background:linear-gradient(145deg,#18336d,#0e1a35 62%,#0b1019)}.hero h1{font-size:38px;line-height:1.12}.hero p,.muted{color:var(--muted)}.formside{padding:42px}.tabs{display:flex;gap:8px;margin-bottom:22px}.tabs button,.nav button{border:0;background:transparent;color:var(--muted);cursor:pointer}.tabs button{padding:9px 14px;border-radius:10px}.tabs button.active,.nav button.active,.nav button:hover{background:#182235;color:#fff}.field{margin:14px 0}.field label{display:block;color:#aebbd0;margin-bottom:6px;font-weight:650}.field input,.field select,.field textarea{width:100%;border:1px solid #2a3953;background:#0a0f18;color:#fff;padding:11px 12px;border-radius:10px}.field textarea{min-height:110px;resize:vertical}.check{display:flex;gap:8px;align-items:flex-start;color:#aebbd0;margin:12px 0}.check input{margin-top:4px}.primary,.secondary,.danger{border:0;border-radius:10px;padding:10px 14px;cursor:pointer;font-weight:700}.primary{background:linear-gradient(135deg,#397cff,#6d6cff);color:#fff}.secondary{background:#1c2636;color:#dce8fb;border:1px solid #2e3a50}.danger{background:#4a1e29;color:#ffb4bf}.wide{width:100%}.shell{display:grid;grid-template-columns:240px 1fr;min-height:100vh}.sidebar{background:#0c111a;border-right:1px solid #202a3b;padding:20px 14px;position:sticky;top:0;height:100vh}.logo{font-size:17px;font-weight:800;padding:6px 8px 22px}.workspace{margin:0 6px 18px;padding:10px;border:1px solid #263247;border-radius:12px;background:#111824}.nav{display:grid;gap:5px}.nav button{text-align:left;padding:10px 12px;border-radius:10px;width:100%}.side-bottom{position:absolute;left:14px;right:14px;bottom:16px}.userbox{padding:10px;border-top:1px solid #1f2a3a;color:var(--muted)}main{padding:26px 32px 60px;max-width:1500px;width:100%}.topbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:24px}.topbar h1{font-size:24px;margin:0}.grid{display:grid;gap:16px}.stats{grid-template-columns:repeat(5,minmax(130px,1fr))}.stat,.card{background:linear-gradient(180deg,#121925,#0f151f);border:1px solid #222e42;border-radius:16px}.stat,.card{padding:18px}.stat .num{font-size:28px;font-weight:800}.toolbar{display:flex;gap:10px;justify-content:space-between;align-items:center;margin-bottom:16px}.actions{display:flex;gap:8px;flex-wrap:wrap}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;border-bottom:1px solid #202a39;padding:11px 8px;vertical-align:middle}.table th{color:#7f8da4;font-size:12px}.badge{display:inline-flex;padding:3px 8px;border-radius:999px;font-size:11px;font-weight:700;background:#202b3c;color:#aebbd0}.badge.succeeded,.badge.ready,.badge.active{background:#12382f;color:#77e6bd}.badge.failed,.badge.canceled,.badge.expired{background:#41202a;color:#ff9bac}.badge.running,.badge.queued{background:#17355f;color:#86baff}.empty{padding:34px;text-align:center;color:var(--muted);border:1px dashed #29364b;border-radius:13px}.split{display:grid;grid-template-columns:1fr 1fr;gap:16px}.modal-backdrop{position:fixed;inset:0;background:#000a;display:grid;place-items:center;z-index:100;padding:20px}.modal{width:min(640px,100%);max-height:90vh;overflow:auto;background:#111824;border:1px solid #31405a;border-radius:18px;padding:22px}.modal-head{display:flex;justify-content:space-between;align-items:center}.iconbtn{border:0;background:transparent;color:#aebbd0;font-size:24px;cursor:pointer}.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}.toast{position:fixed;right:22px;bottom:22px;background:#182234;border:1px solid #354661;border-radius:12px;padding:12px 16px;z-index:200}.progress{height:6px;background:#263247;border-radius:6px;overflow:hidden;width:120px}.progress i{display:block;height:100%;background:#4f8cff}.code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:#aac2e8}.plan-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}.plan{padding:18px;border:1px solid #293950;border-radius:15px;background:#101722}.plan .price{font-size:28px;font-weight:800}.table-wrap{overflow:auto}@media(max-width:950px){.auth-card{grid-template-columns:1fr}.hero{display:none}.shell{grid-template-columns:80px 1fr}.workspace,.nav span,.side-bottom .userbox{display:none}.nav button{text-align:center}.stats{grid-template-columns:repeat(2,1fr)}main{padding:20px}.split,.plan-grid{grid-template-columns:1fr}}@media(max-width:600px){.shell{display:block}.sidebar{position:fixed;bottom:0;top:auto;height:auto;width:100%;z-index:50}.logo,.workspace,.side-bottom{display:none}.nav{grid-template-columns:repeat(7,1fr)}main{padding:18px 14px 86px}.stats{grid-template-columns:1fr 1fr}.row{grid-template-columns:1fr}}
</style>
<style>
/* Login experience v2 */
.auth{
  position:relative;
  min-height:100vh;
  display:grid;
  place-items:center;
  padding:28px;
  overflow:hidden;
  background:
    radial-gradient(circle at 12% 18%,rgba(34,118,255,.20),transparent 30%),
    radial-gradient(circle at 76% 10%,rgba(62,214,207,.10),transparent 24%),
    radial-gradient(circle at 82% 84%,rgba(106,79,255,.16),transparent 28%),
    linear-gradient(135deg,#060914 0%,#090e1a 46%,#07101d 100%);
}
.auth:before,.auth:after{
  content:"";
  position:absolute;
  border-radius:50%;
  filter:blur(4px);
  pointer-events:none;
}
.auth:before{
  width:420px;height:420px;left:-210px;bottom:-180px;
  background:radial-gradient(circle,rgba(42,112,255,.17),transparent 68%);
}
.auth:after{
  width:360px;height:360px;right:-180px;top:-140px;
  background:radial-gradient(circle,rgba(55,216,199,.12),transparent 68%);
}
.auth-card{
  position:relative;
  z-index:1;
  width:min(1240px,calc(100vw - 56px));
  min-height:720px;
  display:grid;
  grid-template-columns:minmax(0,1.12fr) minmax(420px,.88fr);
  overflow:hidden;
  border:1px solid rgba(140,170,220,.18);
  border-radius:30px;
  background:rgba(11,16,28,.82);
  box-shadow:0 34px 100px rgba(0,0,0,.42),0 0 0 1px rgba(255,255,255,.025) inset;
  backdrop-filter:blur(24px);
}
.auth .hero{
  position:relative;
  display:flex;
  flex-direction:column;
  padding:46px 54px 38px;
  overflow:hidden;
  background:
    linear-gradient(145deg,rgba(34,86,185,.25),rgba(8,16,30,.08) 44%,rgba(8,12,22,.1)),
    linear-gradient(180deg,rgba(255,255,255,.03),transparent 50%);
}
.auth .hero:after{
  content:"";
  position:absolute;
  inset:auto -80px -160px auto;
  width:420px;height:420px;
  border-radius:50%;
  background:radial-gradient(circle,rgba(45,217,204,.14),transparent 68%);
  pointer-events:none;
}
.auth-brand{display:flex;align-items:center;gap:12px;color:#fff;font-weight:800;font-size:16px;letter-spacing:.2px}
.auth-logo{
  width:42px;height:42px;border-radius:13px;display:grid;place-items:center;
  background:linear-gradient(145deg,#4ea5ff,#5f55ff);
  box-shadow:0 10px 30px rgba(58,105,255,.35),0 0 0 1px rgba(255,255,255,.22) inset;
}
.auth-logo svg{width:24px;height:24px}
.hero-copy{max-width:620px;margin-top:46px;position:relative;z-index:2}
.auth-kicker{
  display:inline-flex;align-items:center;gap:8px;
  padding:7px 11px;border:1px solid rgba(124,176,255,.18);
  border-radius:999px;background:rgba(70,117,210,.10);
  color:#9dc4ff;font-size:12px;font-weight:750;letter-spacing:.08em;text-transform:uppercase;
}
.auth-kicker i{width:7px;height:7px;border-radius:50%;background:#4de0c8;box-shadow:0 0 14px #4de0c8}
.auth .hero h1{
  margin:18px 0 16px;
  max-width:620px;
  font-size:44px;
  line-height:1.13;
  letter-spacing:-1.8px;
  color:#f6f9ff;
}
.auth .hero h1 span{
  background:linear-gradient(90deg,#7fbcff 0%,#60e3dc 55%,#aa8fff 100%);
  -webkit-background-clip:text;background-clip:text;color:transparent;
}
.auth .hero p{max-width:590px;margin:0;color:#93a5bf;font-size:15px;line-height:1.8}
.hero-visual{
  position:relative;
  z-index:2;
  margin:22px -2px 8px;
  min-height:315px;
  display:grid;
  place-items:center;
}
.hero-art{width:100%;max-width:660px;height:auto;filter:drop-shadow(0 26px 42px rgba(0,0,0,.32))}
.hero-features{display:flex;gap:10px;flex-wrap:wrap;margin-top:auto;position:relative;z-index:2}
.hero-feature{
  display:flex;align-items:center;gap:8px;
  padding:9px 12px;border-radius:12px;
  border:1px solid rgba(137,165,207,.14);
  background:rgba(255,255,255,.035);
  color:#aebcd0;font-size:12px;
}
.hero-feature b{color:#e8f1ff;font-weight:700}
.hero-feature svg{width:16px;height:16px;color:#69c9ff}

.auth .formside{
  display:flex;
  flex-direction:column;
  justify-content:center;
  padding:54px 58px;
  background:linear-gradient(180deg,#fbfdff 0%,#f5f8fd 100%);
  color:#101828;
}
.form-inner{width:100%;max-width:420px;margin:0 auto}
.form-mark{
  display:none;
  width:42px;height:42px;border-radius:13px;place-items:center;margin-bottom:24px;
  background:linear-gradient(145deg,#3f91ff,#665cff);color:#fff;
}
.form-mark svg{width:24px;height:24px}
.form-head{margin-bottom:26px}
.form-head h2{margin:0 0 8px;font-size:30px;line-height:1.2;letter-spacing:-.7px;color:#0d1b32}
.form-head p{margin:0;color:#6b778b;font-size:14px}
.auth .tabs{
  display:grid;
  grid-template-columns:1fr 1fr;
  gap:4px;
  padding:4px;
  margin:0 0 24px;
  border:1px solid #e1e7f0;
  border-radius:13px;
  background:#eef3f9;
}
.auth .tabs button{
  border:0;
  padding:10px 14px;
  border-radius:9px;
  background:transparent;
  color:#718096;
  font-weight:750;
  cursor:pointer;
  transition:.18s ease;
}
.auth .tabs button.active{
  background:#fff;
  color:#1c4fff;
  box-shadow:0 3px 12px rgba(24,50,90,.10);
}
.auth .field{margin:15px 0}
.auth .field label{display:block;margin-bottom:7px;color:#344054;font-size:13px;font-weight:750}
.input-shell{position:relative}
.input-shell .input-icon{
  position:absolute;left:13px;top:50%;transform:translateY(-50%);
  width:18px;height:18px;color:#8a98ab;pointer-events:none;
}
.input-shell .input-icon svg{width:18px;height:18px;display:block}
.auth .field input{
  width:100%;
  height:48px;
  padding:0 14px 0 42px;
  border:1px solid #d8e0ec;
  border-radius:12px;
  outline:0;
  background:#fff;
  color:#172033;
  box-shadow:0 1px 2px rgba(16,24,40,.02);
  transition:border-color .18s,box-shadow .18s,background .18s;
}
.auth .field input::placeholder{color:#a5afbe}
.auth .field input:focus{
  border-color:#5f83ff;
  box-shadow:0 0 0 4px rgba(78,112,255,.11);
  background:#fff;
}
.auth .primary.wide{
  height:49px;
  margin-top:8px;
  border:0;
  border-radius:12px;
  background:linear-gradient(110deg,#2f78ff 0%,#5b65f5 58%,#7358ec 100%);
  color:#fff;
  font-size:14px;
  font-weight:800;
  letter-spacing:.15px;
  box-shadow:0 12px 24px rgba(55,93,229,.22);
  transition:transform .16s ease,box-shadow .16s ease,filter .16s ease;
}
.auth .primary.wide:hover{transform:translateY(-1px);box-shadow:0 15px 30px rgba(55,93,229,.28);filter:saturate(1.06)}
.auth .primary.wide:active{transform:translateY(0)}
.auth-note{
  display:flex;align-items:flex-start;gap:9px;
  margin-top:18px;padding:12px 13px;
  border:1px solid #e4e9f1;border-radius:11px;
  background:#f9fbfe;color:#728095;font-size:12px;line-height:1.55;
}
.auth-note svg{width:16px;height:16px;min-width:16px;margin-top:1px;color:#4c7cff}
.auth-trust{
  display:flex;align-items:center;justify-content:center;gap:14px;flex-wrap:wrap;
  margin-top:24px;padding-top:20px;border-top:1px solid #e7ebf1;
  color:#8a96a8;font-size:11px;
}
.auth-trust span{display:inline-flex;align-items:center;gap:5px}
.auth-trust i{width:5px;height:5px;border-radius:50%;background:#4ccbb8}
.auth-copyright{margin-top:22px;text-align:center;color:#a1aab8;font-size:11px}
@media(max-width:1050px){
  .auth-card{grid-template-columns:1fr minmax(390px,.82fr)}
  .auth .hero{padding:42px 38px 34px}
  .auth .hero h1{font-size:38px}
  .auth .formside{padding:48px 42px}
}
@media(max-width:900px){
  .auth{padding:18px}
  .auth-card{width:min(560px,100%);min-height:auto;grid-template-columns:1fr}
  .auth .hero{display:none}
  .auth .formside{padding:44px 38px}
  .form-mark{display:grid}
}
@media(max-width:520px){
  .auth{padding:0;background:#f6f9fd}
  .auth-card{width:100%;min-height:100vh;border:0;border-radius:0;box-shadow:none}
  .auth .formside{padding:34px 22px}
  .form-head h2{font-size:27px}
}
</style>
</head>
<body>
<section id="authView" class="auth">
  <div class="auth-card">
    <div class="hero">
      <div class="auth-brand">
        <div class="auth-logo" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M7.4 6.1 12 3.4l4.6 2.7v5.3L12 14.1l-4.6-2.7V6.1Z" fill="currentColor" opacity=".95"/>
            <path d="M5.2 13.2 12 17l6.8-3.8v4L12 21l-6.8-3.8v-4Z" fill="currentColor" opacity=".62"/>
          </svg>
        </div>
        <span>Digital Human Studio</span>
      </div>

      <div class="hero-copy">
        <div class="auth-kicker"><i></i> AI DIGITAL CONTENT WORKSPACE</div>
        <h1>让每一份课件，<br>都拥有<span>会讲课的数字人</span></h1>
        <p>从 PPT、讲稿和克隆音色，到数字人合成、字幕与成片交付，一套工作台完成完整的微课生产流程。</p>
      </div>

      <div class="hero-visual" aria-hidden="true">
        <svg class="hero-art" viewBox="0 0 700 360" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="gFrame" x1="110" y1="64" x2="554" y2="310" gradientUnits="userSpaceOnUse">
              <stop stop-color="#1A315D"/><stop offset=".55" stop-color="#10213D"/><stop offset="1" stop-color="#0D172A"/>
            </linearGradient>
            <linearGradient id="gBlue" x1="0" y1="0" x2="1" y2="1">
              <stop stop-color="#4CB5FF"/><stop offset=".58" stop-color="#4378FF"/><stop offset="1" stop-color="#745AF1"/>
            </linearGradient>
            <linearGradient id="gMint" x1="0" y1="0" x2="1" y2="1">
              <stop stop-color="#52E4D0"/><stop offset="1" stop-color="#3E7CFF"/>
            </linearGradient>
            <linearGradient id="gWave" x1="229" y1="153" x2="500" y2="224" gradientUnits="userSpaceOnUse">
              <stop stop-color="#4EA5FF"/><stop offset="1" stop-color="#4DE0C8"/>
            </linearGradient>
            <filter id="shadow" x="-40%" y="-40%" width="180%" height="180%">
              <feDropShadow dx="0" dy="16" stdDeviation="14" flood-color="#000" flood-opacity=".30"/>
            </filter>
            <filter id="soft" x="-40%" y="-40%" width="180%" height="180%">
              <feGaussianBlur stdDeviation="12"/>
            </filter>
          </defs>

          <ellipse cx="357" cy="316" rx="214" ry="24" fill="#142B52" opacity=".48" filter="url(#soft)"/>
          <path d="M106 118C160 55 246 31 340 49c113 22 206 94 250 187" stroke="#2C5FA7" stroke-opacity=".34" stroke-width="1.4"/>
          <path d="M88 246c74 45 152 59 237 42 85-17 161-60 227-128" stroke="#42D7C2" stroke-opacity=".24" stroke-width="1.4"/>
          <circle cx="106" cy="118" r="5" fill="#5AE0CD"/>
          <circle cx="590" cy="236" r="5" fill="#6C72FF"/>

          <g filter="url(#shadow)">
            <rect x="116" y="66" width="470" height="238" rx="22" fill="url(#gFrame)" stroke="#5077B1" stroke-opacity=".45"/>
            <rect x="132" y="82" width="438" height="34" rx="10" fill="#172B4B"/>
            <circle cx="151" cy="99" r="4" fill="#4B91FF"/>
            <circle cx="165" cy="99" r="4" fill="#4DDFC9"/>
            <circle cx="179" cy="99" r="4" fill="#8264F5"/>
            <rect x="466" y="93" width="84" height="11" rx="5.5" fill="#24426D"/>

            <rect x="132" y="128" width="112" height="160" rx="14" fill="#102038"/>
            <rect x="146" y="143" width="84" height="48" rx="11" fill="url(#gBlue)" opacity=".94"/>
            <rect x="155" y="151" width="28" height="31" rx="7" fill="#EAF3FF" opacity=".92"/>
            <circle cx="169" cy="161" r="5" fill="#4C82FF"/>
            <path d="M159 177c2-7 6-10 10-10 5 0 9 3 11 10" stroke="#4C82FF" stroke-width="4" stroke-linecap="round"/>
            <rect x="191" y="154" width="29" height="5" rx="2.5" fill="#DCE9FF" opacity=".92"/>
            <rect x="191" y="165" width="22" height="4" rx="2" fill="#C7DAFF" opacity=".68"/>
            <rect x="191" y="175" width="26" height="4" rx="2" fill="#C7DAFF" opacity=".48"/>

            <rect x="146" y="207" width="84" height="12" rx="6" fill="#1D3557"/>
            <rect x="146" y="226" width="65" height="12" rx="6" fill="#1D3557"/>
            <rect x="146" y="245" width="73" height="12" rx="6" fill="#1D3557"/>

            <rect x="258" y="128" width="297" height="102" rx="14" fill="#F6F9FF"/>
            <rect x="275" y="145" width="72" height="7" rx="3.5" fill="#BDD1EE"/>
            <rect x="275" y="158" width="46" height="5" rx="2.5" fill="#DAE5F4"/>
            <path d="M276 202c24-12 44-29 66-19 21 10 24 25 50 18 27-7 31-28 56-23 20 4 29 20 51 5 13-9 25-20 39-26" stroke="url(#gWave)" stroke-width="4" stroke-linecap="round"/>
            <path d="M276 202c24-12 44-29 66-19 21 10 24 25 50 18 27-7 31-28 56-23 20 4 29 20 51 5 13-9 25-20 39-26v49H276v-4Z" fill="url(#gWave)" opacity=".12"/>
            <circle cx="342" cy="183" r="5" fill="#4E9FFF" stroke="white" stroke-width="3"/>
            <circle cx="448" cy="178" r="5" fill="#4DDECA" stroke="white" stroke-width="3"/>
            <circle cx="538" cy="157" r="5" fill="#51DCC8" stroke="white" stroke-width="3"/>

            <rect x="258" y="242" width="91" height="46" rx="12" fill="#162B49"/>
            <rect x="363" y="242" width="91" height="46" rx="12" fill="#162B49"/>
            <rect x="468" y="242" width="87" height="46" rx="12" fill="#162B49"/>
            <rect x="274" y="256" width="25" height="17" rx="5" fill="url(#gBlue)"/>
            <rect x="307" y="256" width="26" height="5" rx="2.5" fill="#5E789F"/>
            <rect x="307" y="267" width="19" height="4" rx="2" fill="#40597B"/>
            <circle cx="385" cy="264" r="11" fill="url(#gMint)"/>
            <path d="m381 264 3 3 6-7" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            <rect x="404" y="256" width="31" height="5" rx="2.5" fill="#5E789F"/>
            <rect x="404" y="267" width="24" height="4" rx="2" fill="#40597B"/>
            <path d="M485 272v-15m11 15v-22m11 22v-10m11 10v-28" stroke="url(#gBlue)" stroke-width="7" stroke-linecap="round"/>
          </g>

          <g filter="url(#shadow)">
            <rect x="60" y="185" width="128" height="74" rx="17" fill="#F4F8FF"/>
            <rect x="75" y="201" width="42" height="42" rx="12" fill="url(#gBlue)"/>
            <path d="M88 215h16v13H88z" stroke="white" stroke-width="2.5" stroke-linejoin="round"/>
            <path d="m89 214 7-5 7 5" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            <rect x="127" y="207" width="43" height="6" rx="3" fill="#97B6DF"/>
            <rect x="127" y="220" width="32" height="5" rx="2.5" fill="#C0D2E9"/>
            <rect x="127" y="231" width="38" height="5" rx="2.5" fill="#D1DEEE"/>
          </g>

          <g filter="url(#shadow)">
            <rect x="530" y="35" width="118" height="72" rx="17" fill="#F4F8FF"/>
            <rect x="545" y="50" width="42" height="42" rx="12" fill="url(#gMint)"/>
            <path d="M557 74c2-8 5-12 9-12s7 4 9 12" stroke="white" stroke-width="2.6" stroke-linecap="round"/>
            <circle cx="566" cy="59" r="5" fill="white"/>
            <rect x="596" y="56" width="35" height="6" rx="3" fill="#97B6DF"/>
            <rect x="596" y="69" width="28" height="5" rx="2.5" fill="#C4D5EA"/>
          </g>

          <g filter="url(#shadow)">
            <rect x="519" y="271" width="134" height="64" rx="17" fill="#112542" stroke="#416AA7" stroke-opacity=".6"/>
            <circle cx="546" cy="303" r="14" fill="url(#gMint)"/>
            <path d="m540 303 4 4 8-10" stroke="white" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>
            <rect x="568" y="292" width="57" height="6" rx="3" fill="#6686AD"/>
            <rect x="568" y="306" width="42" height="5" rx="2.5" fill="#405E84"/>
          </g>
        </svg>
      </div>

      <div class="hero-features">
        <div class="hero-feature">
          <svg viewBox="0 0 24 24" fill="none"><path d="M5 4h14v16H5zM8 8h8M8 12h6M8 16h5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          <span><b>PPT / 讲稿导入</b> · 智能课程生产</span>
        </div>
        <div class="hero-feature">
          <svg viewBox="0 0 24 24" fill="none"><path d="M12 14a4 4 0 1 0 0-8 4 4 0 0 0 0 8ZM5 20c1.3-3 3.7-4.5 7-4.5S17.7 17 19 20" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
          <span><b>数字人 + 音色</b> 统一资产管理</span>
        </div>
        <div class="hero-feature">
          <svg viewBox="0 0 24 24" fill="none"><path d="m4 12 4 4 12-12M5 20h14" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span><b>异步任务</b> 稳定生成与交付</span>
        </div>
      </div>
    </div>

    <div class="formside">
      <div class="form-inner">
        <div class="form-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M7.4 6.1 12 3.4l4.6 2.7v5.3L12 14.1l-4.6-2.7V6.1Z" fill="currentColor"/>
            <path d="M5.2 13.2 12 17l6.8-3.8v4L12 21l-6.8-3.8v-4Z" fill="currentColor" opacity=".66"/>
          </svg>
        </div>

        <div class="form-head">
          <h2>欢迎进入创作工作台</h2>
          <p>登录后继续管理你的数字人、课程与生成任务。</p>
        </div>

        <div class="tabs">
          <button type="button" data-auth-tab="login" class="active">账号登录</button>
          <button type="button" data-auth-tab="register">注册账号</button>
        </div>

        <form id="loginForm">
          <div class="field">
            <label for="loginEmail">邮箱</label>
            <div class="input-shell">
              <span class="input-icon">
                <svg viewBox="0 0 24 24" fill="none"><path d="M4 6h16v12H4zM4.5 7l7.5 6 7.5-6" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
              </span>
              <input id="loginEmail" type="email" autocomplete="email" placeholder="name@company.com" required>
            </div>
          </div>
          <div class="field">
            <label for="loginPassword">密码</label>
            <div class="input-shell">
              <span class="input-icon">
                <svg viewBox="0 0 24 24" fill="none"><rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
              </span>
              <input id="loginPassword" type="password" autocomplete="current-password" placeholder="请输入密码" required minlength="8">
            </div>
          </div>
          <button class="primary wide">进入工作台</button>
        </form>

        <form id="registerForm" class="hidden">
          <div class="field">
            <label for="regName">姓名</label>
            <div class="input-shell">
              <span class="input-icon">
                <svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="8" r="3.5" stroke="currentColor" stroke-width="1.8"/><path d="M5.5 20c.8-4 3-6 6.5-6s5.7 2 6.5 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
              </span>
              <input id="regName" autocomplete="name" placeholder="你的姓名" required>
            </div>
          </div>
          <div class="field">
            <label for="regEmail">邮箱</label>
            <div class="input-shell">
              <span class="input-icon">
                <svg viewBox="0 0 24 24" fill="none"><path d="M4 6h16v12H4zM4.5 7l7.5 6 7.5-6" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
              </span>
              <input id="regEmail" type="email" autocomplete="email" placeholder="name@company.com" required>
            </div>
          </div>
          <div class="field">
            <label for="regPassword">密码</label>
            <div class="input-shell">
              <span class="input-icon">
                <svg viewBox="0 0 24 24" fill="none"><rect x="5" y="10" width="14" height="10" rx="2" stroke="currentColor" stroke-width="1.8"/><path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
              </span>
              <input id="regPassword" type="password" autocomplete="new-password" placeholder="至少 8 位" required minlength="8">
            </div>
          </div>
          <div class="field">
            <label for="regWorkspace">工作区</label>
            <div class="input-shell">
              <span class="input-icon">
                <svg viewBox="0 0 24 24" fill="none"><path d="M4 20V8l8-4 8 4v12M8 20v-6h8v6" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>
              </span>
              <input id="regWorkspace" value="我的数字人工作室" required>
            </div>
          </div>
          <button class="primary wide">创建账号并进入</button>
        </form>

        <div class="auth-note">
          <svg viewBox="0 0 24 24" fill="none"><path d="M12 3 5 6v5c0 4.6 2.7 8.2 7 10 4.3-1.8 7-5.4 7-10V6l-7-3Z" stroke="currentColor" stroke-width="1.8"/><path d="m9 12 2 2 4-5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span>工作区数据隔离；数字人和声音克隆需确认素材授权；生成内容默认保留 AI 合成标识。</span>
        </div>

        <div class="auth-trust">
          <span><i></i>工作区隔离</span>
          <span><i></i>授权素材管理</span>
          <span><i></i>生成任务可追踪</span>
        </div>
        <div class="auth-copyright">Digital Human Studio · AI 微课生产平台</div>
      </div>
    </div>
  </div>
</section>
<section id="appView" class="shell hidden"><aside class="sidebar"><div class="logo">Digital Human</div><div class="workspace"><small>当前工作区</small><div id="workspaceName">—</div></div><nav class="nav" id="nav"><button data-page="dashboard" class="active">◫ <span>总览</span></button><button data-page="courses">▣ <span>课程</span></button><button data-page="avatars">◉ <span>数字人</span></button><button data-page="assets">◇ <span>素材</span></button><button data-page="jobs">↻ <span>任务</span></button><button data-page="billing">¥ <span>套餐</span></button><button data-page="settings">⚙ <span>设置</span></button><button id="adminNav" class="hidden" data-page="admin">★ <span>运营</span></button></nav><div class="side-bottom"><div class="userbox"><div id="userName">—</div><small id="userEmail">—</small></div><button id="logoutBtn" class="secondary wide">退出</button></div></aside><main><div class="topbar"><div><h1 id="pageTitle">工作台总览</h1><div class="muted" id="pageSubtitle"></div></div><button id="refreshBtn" class="secondary">刷新</button></div><div id="page"></div></main></section>
<div id="modalRoot"></div><div id="toast" class="toast hidden"></div>
<script>
const API='/api/saas';let token=sessionStorage.getItem('dh_token')||'';let current='dashboard';let me=null;let cache={assets:[],avatars:[],voices:[],courses:[]};
const $=id=>document.getElementById(id);function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}function toast(msg){const e=$('toast');e.textContent=msg;e.classList.remove('hidden');setTimeout(()=>e.classList.add('hidden'),2600)}
async function api(path,opt={}){opt.headers=opt.headers||{};if(token)opt.headers.Authorization='Bearer '+token;if(opt.body&&!(opt.body instanceof FormData)&&typeof opt.body!=='string'){opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(opt.body)}const r=await fetch(API+path,opt);if(r.status===401&&path!='/auth/login'){logout();throw Error('登录已失效')}if(r.status===204)return null;const d=await r.json().catch(()=>({}));if(!r.ok)throw Error(typeof d.detail==='string'?d.detail:JSON.stringify(d.detail||d));return d}
function logout(){token='';me=null;sessionStorage.removeItem('dh_token');$('appView').classList.add('hidden');$('authView').classList.remove('hidden')}function openModal(html){$('modalRoot').innerHTML='<div class="modal-backdrop"><div class="modal">'+html+'</div></div>'}function closeModal(){$('modalRoot').innerHTML=''}
async function loadLookups(){const [a,v,av,c]=await Promise.all([api('/assets'),api('/voices'),api('/avatars'),api('/courses')]);cache={assets:a,voices:v,avatars:av,courses:c}}
const titles={dashboard:['工作台总览','掌握课程与生成任务状态'],courses:['课程工作台','从 PPT 到数字人微课'],avatars:['数字人资产','管理讲师母版与克隆音色'],assets:['素材中心','工作区私有文件'],jobs:['生成任务','排队、运行、失败与成片下载'],billing:['套餐与用量','分钟额度、存储与成员上限'],settings:['工作区设置','成员与工作区切换'],admin:['运营管理','平台级用户、工作区与订单']};
async function boot(){if(!token)return logout();try{me=await api('/auth/me');$('authView').classList.add('hidden');$('appView').classList.remove('hidden');$('workspaceName').textContent=me.workspace.name;$('userName').textContent=me.user.display_name;$('userEmail').textContent=me.user.email;$('adminNav').classList.toggle('hidden',!me.user.is_superuser);await loadLookups();await showPage(current)}catch(e){logout()}}
async function showPage(name){current=name;document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===name));$('pageTitle').textContent=titles[name][0];$('pageSubtitle').textContent=titles[name][1];$('page').innerHTML='<div class="card">加载中…</div>';try{await ({dashboard:renderDashboard,courses:renderCourses,avatars:renderAvatars,assets:renderAssets,jobs:renderJobs,billing:renderBilling,settings:renderSettings,admin:renderAdmin}[name])()}catch(e){$('page').innerHTML='<div class="card">'+esc(e.message)+'</div>'}}
function opts(items,value,label='name'){return '<option value="">— 未选择 —</option>'+items.map(x=>`<option value="${x.id}" ${x.id===value?'selected':''}>${esc(x[label])}</option>`).join('')}
async function downloadAsset(id,name){const r=await fetch(API+'/assets/'+id+'/download',{headers:{Authorization:'Bearer '+token}});if(!r.ok)throw Error('下载失败');const blob=await r.blob(),u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download=name||'download';a.click();URL.revokeObjectURL(u)}
async function renderDashboard(){const [d,b,j]=await Promise.all([api('/dashboard'),api('/billing/subscription'),api('/jobs')]);$('page').innerHTML=`<div class="grid stats"><div class="stat"><div class="muted">课程</div><div class="num">${d.courses}</div></div><div class="stat"><div class="muted">数字人</div><div class="num">${d.avatars}</div></div><div class="stat"><div class="muted">素材</div><div class="num">${d.assets}</div></div><div class="stat"><div class="muted">进行中</div><div class="num">${d.active_jobs}</div></div><div class="stat"><div class="muted">已成片</div><div class="num">${d.completed_jobs}</div></div></div><div class="split" style="margin-top:16px"><div class="card"><h2>${esc(b.plan_name)} · ${esc(b.status)}</h2><div style="font-size:32px;font-weight:800">${b.remaining_minutes} 分钟</div><div class="muted">已使用 ${b.consumed_minutes} 分钟 · 存储上限 ${b.storage_gb}GB</div></div><div class="card"><h2>最近任务</h2>${jobTable(j.slice(0,5))}</div></div>`;wirePageActions()}
function courseTable(items){if(!items.length)return '<div class="empty">还没有课程。</div>';return `<div class="table-wrap"><table class="table"><thead><tr><th>课程</th><th>状态</th><th>数字人</th><th>成片</th><th></th></tr></thead><tbody>${items.map(c=>`<tr><td><b>${esc(c.title)}</b><div class="code">${c.id.slice(0,8)}</div></td><td><span class="badge ${c.status}">${esc(c.status)}</span></td><td>${esc(cache.avatars.find(a=>a.id===c.avatar_id)?.name||'未选择')}</td><td>${c.output_asset_id?`<button class="secondary" data-action="download" data-id="${c.output_asset_id}" data-name="${esc(c.title)}.mp4">下载</button>`:'—'}</td><td><button class="secondary" data-action="edit-course" data-id="${c.id}">编辑</button> <button class="primary" data-action="render-course" data-id="${c.id}">生成</button></td></tr>`).join('')}</tbody></table></div>`}
async function renderCourses(){cache.courses=await api('/courses');$('page').innerHTML=`<div class="card"><div class="toolbar"><div><h2>课程项目</h2><div class="muted">课程保存 PPT、讲稿、数字人与音色</div></div><button class="primary" data-action="new-course">+ 新建课程</button></div>${courseTable(cache.courses)}</div>`;wirePageActions()}
function courseModal(c=null){c=c||{title:'',ppt_asset_id:'',avatar_id:'',voice_profile_id:'',script:[]};const ppts=cache.assets.filter(a=>a.kind==='ppt'||a.name.toLowerCase().endsWith('.pptx'));openModal(`<div class="modal-head"><h2>${c.id?'编辑':'新建'}课程</h2><button class="iconbtn" data-close>×</button></div><form id="courseForm" data-id="${c.id||''}"><div class="field"><label>课程名称</label><input id="cTitle" value="${esc(c.title)}" required></div><div class="field"><label>PPT</label><select id="cPpt">${opts(ppts,c.ppt_asset_id)}</select></div><div class="row"><div class="field"><label>数字人</label><select id="cAvatar">${opts(cache.avatars,c.avatar_id)}</select></div><div class="field"><label>音色</label><select id="cVoice">${opts(cache.voices,c.voice_profile_id)}</select></div></div><div class="field"><label>按页讲稿 JSON</label><textarea id="cScript">${esc(JSON.stringify(c.script||[],null,2))}</textarea></div><button class="primary wide">保存</button></form>`);wireModal()}
function renderModal(id){openModal(`<div class="modal-head"><h2>提交生成</h2><button class="iconbtn" data-close>×</button></div><form id="renderForm" data-id="${id}"><div class="field"><label>预计时长（秒，仅作为保守预留提示，服务端会重新估算并按实际成片结算）</label><input id="renderSecs" type="number" min="1" max="21600" value="60"></div><div class="field"><label>引擎</label><select id="renderEngine"><option value="musetalk">MuseTalk</option><option value="mock">Mock 联调</option></select></div><div class="field"><label>已有配音素材（可选）</label><select id="renderAudio">${opts(cache.assets.filter(a=>a.kind==='audio'),'')}</select></div><button class="primary wide">加入队列</button></form>`);wireModal()}
async function renderAvatars(){const [avatars,voices]=await Promise.all([api('/avatars'),api('/voices')]);cache.avatars=avatars;cache.voices=voices;$('page').innerHTML=`<div class="split"><div class="card"><div class="toolbar"><h2>数字人</h2><button class="primary" data-action="new-avatar">+ 添加</button></div>${avatars.length?`<table class="table"><tbody>${avatars.map(a=>`<tr><td><b>${esc(a.name)}</b><div class="muted">${a.master_video_asset_id?'视频母版':'图片人物'}</div></td><td><span class="badge ${a.status}">${esc(a.status)}</span></td><td>${['owner','admin'].includes(me.workspace.role)?`<button class="danger" data-action="delete-avatar" data-id="${a.id}">删除</button>`:''}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无数字人</div>'}</div><div class="card"><div class="toolbar"><h2>克隆音色</h2><button class="primary" data-action="new-voice">+ 添加</button></div>${voices.length?`<table class="table"><tbody>${voices.map(v=>`<tr><td><b>${esc(v.name)}</b><div class="muted">${esc(v.provider)}</div></td><td>${['owner','admin'].includes(me.workspace.role)?`<button class="danger" data-action="delete-voice" data-id="${v.id}">删除</button>`:''}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无克隆音色</div>'}</div></div>`;wirePageActions()}
function avatarModal(){const videos=cache.assets.filter(a=>a.kind==='video'),images=cache.assets.filter(a=>a.kind==='image');openModal(`<div class="modal-head"><h2>添加数字人</h2><button class="iconbtn" data-close>×</button></div><form id="avatarForm"><div class="field"><label>名称</label><input id="aName" required></div><div class="field"><label>母版视频</label><select id="aVideo">${opts(videos,'')}</select></div><div class="field"><label>人物图片（可选）</label><select id="aImage">${opts(images,'')}</select></div><div class="field"><label>默认音色</label><select id="aVoice">${opts(cache.voices,'')}</select></div><div class="field"><label>人物提示词</label><textarea id="aPrompt"></textarea></div><label class="check"><input id="aConsent" type="checkbox" required><span>我确认已取得该人物肖像/视频用于数字人合成的合法授权。</span></label><button class="primary wide">保存数字人</button></form>`);wireModal()}
function voiceModal(){const audios=cache.assets.filter(a=>a.kind==='audio');openModal(`<div class="modal-head"><h2>添加克隆音色</h2><button class="iconbtn" data-close>×</button></div><form id="voiceForm"><div class="field"><label>音色名称</label><input id="vName" required></div><div class="field"><label>参考录音</label><select id="vAudio">${opts(audios,'')}</select></div><div class="field"><label>参考录音逐字稿</label><textarea id="vText"></textarea></div><label class="check"><input id="vConsent" type="checkbox" required><span>我确认已取得该声音用于合成/克隆的合法授权。</span></label><button class="primary wide">保存音色</button></form>`);wireModal()}
async function renderAssets(){cache.assets=await api('/assets');$('page').innerHTML=`<div class="card"><div class="toolbar"><h2>素材中心</h2><button class="primary" data-action="new-asset">+ 上传素材</button></div>${cache.assets.length?`<table class="table"><thead><tr><th>文件</th><th>类型</th><th>大小</th><th></th></tr></thead><tbody>${cache.assets.map(a=>`<tr><td><b>${esc(a.name)}</b></td><td>${esc(a.kind)}</td><td>${(a.size_bytes/1024/1024).toFixed(2)} MB</td><td><button class="secondary" data-action="download" data-id="${a.id}" data-name="${esc(a.name)}">下载</button> ${['owner','admin'].includes(me.workspace.role)&&a.kind!=='output'?`<button class="danger" data-action="delete-asset" data-id="${a.id}">删除</button>`:''}</td></tr>`).join('')}</tbody></table>`:'<div class="empty">暂无素材</div>'}</div>`;wirePageActions()}
function assetModal(){openModal(`<div class="modal-head"><h2>上传素材</h2><button class="iconbtn" data-close>×</button></div><form id="assetForm"><div class="field"><label>素材类型</label><select id="assetKind"><option value="ppt">PPT课件</option><option value="video">讲师视频</option><option value="audio">参考录音/配音</option><option value="image">人物/图片</option><option value="background">背景图</option><option value="document">文档</option><option value="other">其他</option></select></div><div class="field"><label>选择文件</label><input id="assetFile" type="file" required></div><button class="primary wide">上传</button></form>`);wireModal()}
function jobTable(items){if(!items.length)return '<div class="empty">暂无生成任务</div>';return `<table class="table"><thead><tr><th>任务</th><th>状态</th><th>进度</th><th>引擎</th><th>结果</th><th></th></tr></thead><tbody>${items.map(j=>`<tr><td class="code">${j.id.slice(0,12)}</td><td><span class="badge ${j.status}">${esc(j.status)}</span><div class="muted">${esc(j.stage||'')}</div></td><td><div class="progress"><i style="width:${j.progress||0}%"></i></div></td><td>${esc(j.engine)}</td><td>${j.output_asset_id?`<button class="secondary" data-action="download" data-id="${j.output_asset_id}" data-name="result.mp4">下载</button>`:'—'}</td><td>${j.status==='queued'?`<button class="danger" data-action="cancel-job" data-id="${j.id}">取消</button>`:''}</td></tr>`).join('')}</tbody></table>`}
async function renderJobs(){const jobs=await api('/jobs');$('page').innerHTML=`<div class="card"><h2>生成队列</h2>${jobTable(jobs)}</div>`;wirePageActions()}
async function renderBilling(){const [plans,sub,orders]=await Promise.all([api('/billing/plans'),api('/billing/subscription'),api('/billing/orders')]);$('page').innerHTML=`<div class="card" style="margin-bottom:16px"><h2>当前套餐：${esc(sub.plan_name)}</h2><div style="font-size:28px;font-weight:800">${sub.remaining_minutes} 分钟</div><div class="muted">状态 ${esc(sub.status)} · 已使用 ${sub.consumed_minutes} 分钟 · 存储 ${sub.storage_gb}GB · 数字人 ${sub.max_avatars} · 成员 ${sub.max_members}</div></div><div class="plan-grid">${plans.map(p=>`<div class="plan"><h3>${esc(p.name)}</h3><div class="price">¥${p.price_cny}<small class="muted"> / 30天</small></div><p>${p.monthly_minutes} 分钟 · ${p.storage_gb}GB · ${p.max_avatars} 数字人 · ${p.max_members} 成员</p>${['owner','admin'].includes(me.workspace.role)?`<button class="primary wide" data-action="order-plan" data-code="${p.code}">创建人工确认订单</button>`:''}</div>`).join('')}</div>${orders.length?`<div class="card" style="margin-top:16px"><h2>订单</h2><table class="table"><tbody>${orders.slice(0,10).map(o=>`<tr><td>${esc(o.plan_code)}</td><td>¥${o.amount_cny}</td><td><span class="badge ${o.status}">${esc(o.status)}</span></td><td>${new Date(o.created_at).toLocaleString()}</td></tr>`).join('')}</tbody></table></div>`:''}`;wirePageActions()}
async function renderSettings(){const members=await api('/workspaces/members');$('page').innerHTML=`<div class="split"><div class="card"><h2>工作区</h2><div class="field"><label>当前工作区</label><select id="workspaceSwitch">${me.workspaces.map(w=>`<option value="${w.id}" ${w.id===me.workspace.id?'selected':''}>${esc(w.name)} · ${esc(w.role)}</option>`).join('')}</select></div><button class="secondary" data-action="new-workspace">+ 新建工作区</button></div><div class="card"><div class="toolbar"><h2>成员</h2>${me.workspace.role==='owner'?'<button class="primary" data-action="new-member">+ 添加成员</button>':''}</div><table class="table"><tbody>${members.map(m=>`<tr><td><b>${esc(m.display_name)}</b><div class="muted">${esc(m.email)}</div></td><td>${esc(m.role)}</td><td>${me.workspace.role==='owner'&&m.role!=='owner'?`<button class="danger" data-action="remove-member" data-id="${m.id}">移除</button>`:''}</td></tr>`).join('')}</tbody></table></div></div>`;wirePageActions();$('workspaceSwitch').addEventListener('change',switchWorkspace)}
function memberModal(){openModal(`<div class="modal-head"><h2>添加成员</h2><button class="iconbtn" data-close>×</button></div><form id="memberForm"><div class="field"><label>已注册邮箱</label><input id="memberEmail" type="email" required></div><div class="field"><label>角色</label><select id="memberRole"><option value="member">成员</option><option value="admin">管理员</option></select></div><button class="primary wide">添加</button></form>`);wireModal()}
function workspaceModal(){openModal(`<div class="modal-head"><h2>新建工作区</h2><button class="iconbtn" data-close>×</button></div><form id="workspaceForm"><div class="field"><label>工作区名称</label><input id="workspaceNewName" required></div><div class="muted" style="margin-bottom:12px">每个账号只有首个工作区获得免费体验额度；额外工作区初始额度为 0。</div><button class="primary wide">创建</button></form>`);wireModal()}
async function renderAdmin(){if(!me.user.is_superuser){$('page').innerHTML='<div class="card">无权限</div>';return}const [o,tenants,orders,workers]=await Promise.all([api('/admin/overview'),api('/admin/tenants'),api('/admin/orders'),api('/distributed/workers')]);window.__tenants=Object.fromEntries(tenants.map(t=>[t.id,t]));const workerRows=workers.map(w=>{const status=w.status||'offline',seen=w.last_seen_at?new Date(w.last_seen_at).toLocaleString():'尚未连接',version=[w.code_version,w.model_version].filter(Boolean).join(' / ')||'—';let actions='';if(status!=='revoked'&&status!=='pending'){actions+=`<button class="secondary" data-action="toggle-worker" data-id="${w.id}" data-accepting="${w.accepting_tasks?'1':'0'}">${w.accepting_tasks?'暂停接任务':'恢复接任务'}</button> `}if(status!=='revoked'&&!w.slots_busy){actions+=`<button class="danger" data-action="revoke-worker" data-id="${w.id}">吊销</button>`}return `<tr><td><strong>${esc(w.name)}</strong><div class="code">${w.id.slice(0,10)}</div></td><td><span class="badge ${esc(status)}">${esc(status)}</span><div class="muted">${w.slots_busy||0}/${w.slots_total||1} 槽位</div></td><td>${esc(w.host||'—')}<div class="muted">${esc(seen)}</div></td><td class="code">${esc(version)}</td><td><div class="actions">${actions}</div></td></tr>`}).join('');$('page').innerHTML=`<div class="grid stats"><div class="stat"><div class="muted">用户</div><div class="num">${o.users}</div></div><div class="stat"><div class="muted">工作区</div><div class="num">${o.tenants}</div></div><div class="stat"><div class="muted">排队</div><div class="num">${o.queued_jobs}</div></div><div class="stat"><div class="muted">运行</div><div class="num">${o.running_jobs}</div></div><div class="stat"><div class="muted">待确认</div><div class="num">${o.pending_orders}</div></div></div><div class="card" style="margin-top:16px"><div class="toolbar"><div><h2 style="margin:0">远程算力 Worker</h2><div class="muted">公网 / 局域网 Mac 统一接入、Drain 与凭据吊销</div></div><button class="primary" data-action="new-worker-enrollment">＋ 新增远程 Worker</button></div><div class="table-wrap"><table class="table"><thead><tr><th>节点</th><th>状态</th><th>主机 / 最近在线</th><th>版本</th><th>操作</th></tr></thead><tbody>${workerRows||'<tr><td colspan="5" class="muted">暂无远程 Worker</td></tr>'}</tbody></table></div></div><div class="card" style="margin-top:16px"><h2>工作区</h2><table class="table"><tbody>${tenants.map(t=>`<tr><td>${esc(t.name)}<div class="code">${t.id.slice(0,8)}</div></td><td>${esc(t.plan_code||'-')}</td><td>${t.remaining_minutes} 分钟</td><td><button class="secondary" data-action="credit" data-id="${t.id}">调整额度</button></td></tr>`).join('')}</tbody></table></div><div class="card" style="margin-top:16px"><h2>待确认订单</h2><table class="table"><tbody>${orders.filter(x=>x.status==='pending').map(o=>`<tr><td>${o.id.slice(0,10)}</td><td>${esc(o.plan_code)}</td><td>¥${o.amount_cny}</td><td><button class="primary" data-action="mark-paid" data-id="${o.id}">确认收款</button></td></tr>`).join('')||'<tr><td class="muted">暂无</td></tr>'}</tbody></table></div>`;wirePageActions()}
function workerEnrollmentModal(){openModal(`<div class="modal-head"><div><h2 style="margin-bottom:4px">新增远程 Worker</h2><div class="muted">生成短时一次性注册码，长期凭据由目标 Mac 自动写入 Keychain。</div></div><button class="iconbtn" data-close>×</button></div><form id="workerEnrollmentForm"><div class="field"><label>Worker 名称</label><input id="workerEnrollName" value="remote-mac-01" required></div><div class="field"><label>并发槽位</label><input id="workerEnrollSlots" type="number" min="1" max="4" value="1" required></div><button class="primary wide">生成注册码</button></form>`);wireModal()}
function workerEnrollmentResult(data){const code=data.enrollment_code||'',expires=data.expires_at?new Date(data.expires_at).toLocaleString():'—',center=location.origin+API+'/internal/render';openModal(`<div class="modal-head"><div><h2 style="margin-bottom:4px">远程 Worker 注册码</h2><div class="muted">仅显示本次注册码；使用后立即失效。</div></div><button class="iconbtn" data-close>×</button></div><div class="field"><label>Enrollment Code</label><textarea id="workerEnrollmentCode" class="code" readonly style="min-height:78px">${esc(code)}</textarea></div><div class="muted" style="margin-bottom:14px">有效期至 ${esc(expires)}</div><div class="card" style="padding:14px;margin-bottom:14px"><div class="muted">目标 Mac 执行</div><div class="code" style="margin-top:8px;white-space:pre-wrap">python -m app.saas.remote_worker_agent enroll \\\n  --center ${esc(center)} \\\n  --name ${esc(data.worker?.name||'remote-mac-01')} \\\n  --install</div></div><div class="actions"><button class="primary" type="button" data-copy-enrollment>复制注册码</button><button class="secondary" type="button" data-close>关闭</button></div>`);wireModal()}
function creditModal(id){const t=(window.__tenants||{})[id]||{name:'工作区'};openModal(`<div class="modal-head"><h2>调整额度</h2><button class="iconbtn" data-close>×</button></div><div class="muted">${esc(t.name)}</div><form id="creditForm" data-id="${id}"><div class="field"><label>分钟（负数可扣减）</label><input id="creditMins" type="number" value="60" required></div><div class="field"><label>原因</label><input id="creditReason" value="运营调整"></div><button class="primary wide">确认</button></form>`);wireModal()}
function wirePageActions(){$('page').querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',async()=>{const a=b.dataset.action,id=b.dataset.id;try{if(a==='new-course')courseModal();else if(a==='edit-course')courseModal(await api('/courses/'+id));else if(a==='render-course')renderModal(id);else if(a==='new-avatar')avatarModal();else if(a==='new-voice')voiceModal();else if(a==='new-asset')assetModal();else if(a==='download')await downloadAsset(id,b.dataset.name);else if(a==='delete-asset'){if(confirm('删除素材？')){await api('/assets/'+id,{method:'DELETE'});await loadLookups();showPage('assets')}}else if(a==='delete-avatar'){if(confirm('删除数字人？')){await api('/avatars/'+id,{method:'DELETE'});await loadLookups();showPage('avatars')}}else if(a==='delete-voice'){if(confirm('删除音色？')){await api('/voices/'+id,{method:'DELETE'});await loadLookups();showPage('avatars')}}else if(a==='cancel-job'){await api('/jobs/'+id+'/cancel',{method:'POST'});showPage('jobs')}else if(a==='order-plan'){await api('/billing/orders',{method:'POST',body:{plan_code:b.dataset.code,provider:'manual'}});toast('订单已创建，等待管理员确认');showPage('billing')}else if(a==='new-member')memberModal();else if(a==='remove-member'){if(confirm('移除成员？')){await api('/workspaces/members/'+id,{method:'DELETE'});showPage('settings')}}else if(a==='new-workspace')workspaceModal();else if(a==='credit')creditModal(id);else if(a==='mark-paid'){await api('/admin/orders/'+id+'/mark-paid',{method:'POST'});showPage('admin')}else if(a==='new-worker-enrollment')workerEnrollmentModal();else if(a==='toggle-worker'){await api('/distributed/workers/'+id+'/accepting',{method:'PATCH',body:{accepting_tasks:b.dataset.accepting!=='1'}});showPage('admin')}else if(a==='revoke-worker'){if(confirm('吊销后该 Worker 的现有凭据将立即失效，确定继续？')){await api('/distributed/workers/'+id+'/revoke',{method:'POST'});showPage('admin')}}}catch(e){toast(e.message)}}))}
function wireModal(){$('modalRoot').querySelectorAll('[data-close]').forEach(b=>b.addEventListener('click',closeModal));const forms=$('modalRoot').querySelectorAll('form');forms.forEach(f=>f.addEventListener('submit',async e=>{e.preventDefault();try{if(f.id==='courseForm'){const script=JSON.parse($('cScript').value||'[]'),id=f.dataset.id;await api('/courses'+(id?'/'+id:''),{method:id?'PATCH':'POST',body:{title:$('cTitle').value,ppt_asset_id:$('cPpt').value||null,avatar_id:$('cAvatar').value||null,voice_profile_id:$('cVoice').value||null,script}});await loadLookups();closeModal();showPage('courses')}else if(f.id==='renderForm'){await api('/courses/'+f.dataset.id+'/render',{method:'POST',body:{engine:$('renderEngine').value,estimated_seconds:Number($('renderSecs').value),audio_asset_id:$('renderAudio').value||null}});closeModal();showPage('jobs')}else if(f.id==='avatarForm'){await api('/avatars',{method:'POST',body:{name:$('aName').value,master_video_asset_id:$('aVideo').value||null,image_asset_id:$('aImage').value||null,voice_profile_id:$('aVoice').value||null,prompt:$('aPrompt').value,consent_confirmed:$('aConsent').checked}});await loadLookups();closeModal();showPage('avatars')}else if(f.id==='voiceForm'){await api('/voices',{method:'POST',body:{name:$('vName').value,provider:'cosyvoice',reference_asset_id:$('vAudio').value||null,transcript:$('vText').value,consent_confirmed:$('vConsent').checked}});await loadLookups();closeModal();showPage('avatars')}else if(f.id==='assetForm'){const fd=new FormData();fd.append('file',$('assetFile').files[0]);fd.append('kind',$('assetKind').value);await api('/assets',{method:'POST',body:fd});await loadLookups();closeModal();showPage('assets')}else if(f.id==='memberForm'){await api('/workspaces/members',{method:'POST',body:{email:$('memberEmail').value,role:$('memberRole').value}});closeModal();showPage('settings')}else if(f.id==='workspaceForm'){await api('/workspaces',{method:'POST',body:{name:$('workspaceNewName').value}});closeModal();me=await api('/auth/me');showPage('settings')}else if(f.id==='creditForm'){await api('/admin/credits',{method:'POST',body:{tenant_id:f.dataset.id,minutes:Number($('creditMins').value),reason:$('creditReason').value}});closeModal();showPage('admin')}else if(f.id==='workerEnrollmentForm'){const data=await api('/distributed/workers/enrollments',{method:'POST',body:{name:$('workerEnrollName').value,slots_total:Number($('workerEnrollSlots').value)}});workerEnrollmentResult(data)}}catch(e){toast(e.message)}}));$('modalRoot').querySelectorAll('[data-copy-enrollment]').forEach(b=>b.addEventListener('click',async()=>{const e=$('workerEnrollmentCode');if(!e)return;try{await navigator.clipboard.writeText(e.value);toast('注册码已复制')}catch(_){e.select();document.execCommand('copy');toast('注册码已复制')}}))}
async function switchWorkspace(e){try{const d=await api('/auth/switch-workspace/'+e.target.value,{method:'POST'});token=d.access_token;sessionStorage.setItem('dh_token',token);await boot()}catch(err){toast(err.message)}}
document.querySelectorAll('[data-auth-tab]').forEach(b=>b.addEventListener('click',()=>{const t=b.dataset.authTab;document.querySelectorAll('[data-auth-tab]').forEach(x=>x.classList.toggle('active',x===b));$('loginForm').classList.toggle('hidden',t!=='login');$('registerForm').classList.toggle('hidden',t!=='register')}));$('loginForm').addEventListener('submit',async e=>{e.preventDefault();try{const d=await api('/auth/login',{method:'POST',body:{email:$('loginEmail').value,password:$('loginPassword').value}});token=d.access_token;sessionStorage.setItem('dh_token',token);boot()}catch(err){toast(err.message)}});$('registerForm').addEventListener('submit',async e=>{e.preventDefault();try{const d=await api('/auth/register',{method:'POST',body:{email:$('regEmail').value,password:$('regPassword').value,display_name:$('regName').value,workspace_name:$('regWorkspace').value}});token=d.access_token;sessionStorage.setItem('dh_token',token);boot()}catch(err){toast(err.message)}});$('nav').addEventListener('click',e=>{const b=e.target.closest('button[data-page]');if(b)showPage(b.dataset.page)});$('logoutBtn').addEventListener('click',logout);$('refreshBtn').addEventListener('click',()=>loadLookups().then(()=>showPage(current)));$('modalRoot').addEventListener('click',e=>{if(e.target.classList.contains('modal-backdrop'))closeModal()});setInterval(()=>{if(token&&current==='jobs')renderJobs().catch(()=>{})},5000);boot();
</script>
</body></html>'''


def dashboard_html() -> HTMLResponse:
    return HTMLResponse(HTML)
