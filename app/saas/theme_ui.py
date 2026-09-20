from __future__ import annotations

from fastapi.responses import Response


CSS = r'''
:root{
  --bg:#07090d;--bg2:#0a0d12;--panel:rgba(15,19,26,.82);--panel-solid:#0f131a;
  --panel2:#131923;--line:rgba(151,176,214,.13);--line-strong:rgba(119,180,255,.28);
  --text:#f3f7ff;--muted:#8996aa;--muted2:#657286;--brand:#71b7ff;--brand2:#9ad7ff;
  --cyan:#72e6ff;--good:#63d6ad;--warn:#efc06e;--bad:#ff738c;
  --shadow:0 24px 80px rgba(0,0,0,.38);--glow:0 0 0 1px rgba(113,183,255,.08),0 16px 48px rgba(0,0,0,.28);
  --radius:18px;--radius-sm:12px;
}
*{box-sizing:border-box}
html{background:var(--bg)}
body{margin:0;color:var(--text);font:14px/1.6 -apple-system,BlinkMacSystemFont,"SF Pro Display","Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;background:
radial-gradient(900px 560px at 88% -10%,rgba(62,132,255,.10),transparent 62%),
radial-gradient(760px 520px at -10% 96%,rgba(50,220,255,.06),transparent 66%),
linear-gradient(180deg,#080a0f 0%,#07090d 100%);letter-spacing:.01em}
body:before{content:"";position:fixed;inset:0;pointer-events:none;opacity:.20;background-image:linear-gradient(rgba(140,180,230,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(140,180,230,.035) 1px,transparent 1px);background-size:44px 44px;mask-image:linear-gradient(to bottom,rgba(0,0,0,.65),transparent 78%)}
button,input,select,textarea{font:inherit}
button{transition:transform .16s ease,border-color .16s ease,background .16s ease,color .16s ease,box-shadow .16s ease}
button:active{transform:translateY(1px)}
.hidden{display:none!important}.muted{color:var(--muted)}
.auth{min-height:100vh;display:grid;place-items:center;padding:32px;position:relative}
.auth-card{width:min(1000px,100%);min-height:580px;display:grid;grid-template-columns:1.08fr .92fr;background:rgba(10,13,18,.88);border:1px solid var(--line);border-radius:28px;overflow:hidden;box-shadow:0 36px 120px rgba(0,0,0,.55);backdrop-filter:blur(24px)}
.hero{position:relative;padding:72px 64px;background:linear-gradient(155deg,rgba(22,30,43,.94),rgba(9,13,20,.98));overflow:hidden}
.hero:before{content:"";position:absolute;width:420px;height:420px;border:1px solid rgba(114,230,255,.14);border-radius:50%;right:-180px;top:-90px;box-shadow:0 0 70px rgba(55,146,255,.09)}
.hero:after{content:"";position:absolute;width:220px;height:220px;border:1px solid rgba(113,183,255,.12);border-radius:50%;right:20px;top:105px}
.hero h1{font-size:46px;line-height:1.06;letter-spacing:-.04em;margin:0 0 24px;background:linear-gradient(180deg,#fff,#b8c9e1);-webkit-background-clip:text;color:transparent}
.hero p{max-width:470px;font-size:15px;color:#8796ac}.hero p:first-of-type{font-size:17px;color:#b7c4d6}
.formside{padding:62px 54px;display:flex;flex-direction:column;justify-content:center;background:rgba(8,11,16,.76)}
.tabs{display:flex;gap:4px;padding:4px;background:#0c1118;border:1px solid var(--line);border-radius:14px;margin-bottom:28px;width:max-content}
.tabs button,.nav button{border:0;background:transparent;color:var(--muted);cursor:pointer}
.tabs button{padding:8px 17px;border-radius:10px;font-weight:650}.tabs button.active{background:#182230;color:#eef6ff;box-shadow:inset 0 0 0 1px rgba(113,183,255,.12)}
.field{margin:15px 0}.field label{display:block;color:#b5c0cf;margin-bottom:7px;font-size:13px;font-weight:650}
.field input,.field select,.field textarea{width:100%;border:1px solid var(--line);background:#0a0e14;color:#eef5ff;padding:12px 13px;border-radius:12px;outline:none;transition:border .15s,box-shadow .15s,background .15s}
.field input:focus,.field select:focus,.field textarea:focus{border-color:rgba(113,183,255,.55);box-shadow:0 0 0 3px rgba(113,183,255,.08);background:#0c1118}.field textarea{min-height:112px;resize:vertical}
.check{display:flex;gap:9px;align-items:flex-start;color:#9ba8ba;margin:12px 0}.check input{margin-top:5px;accent-color:#75baff}
.primary,.secondary,.danger{border-radius:11px;padding:10px 15px;cursor:pointer;font-weight:680;letter-spacing:.01em}
.primary{border:1px solid rgba(145,204,255,.32);background:linear-gradient(180deg,#2b80cb,#216cae);color:white;box-shadow:0 8px 24px rgba(29,104,170,.20)}
.primary:hover{background:linear-gradient(180deg,#338bd7,#2475bd);box-shadow:0 10px 30px rgba(48,132,204,.26)}
.secondary{background:#111821;color:#c6d2e3;border:1px solid var(--line)}.secondary:hover{border-color:var(--line-strong);color:#fff;background:#141d29}
.danger{background:rgba(255,91,116,.07);color:#ff8ca0;border:1px solid rgba(255,115,140,.18)}.danger:hover{background:rgba(255,91,116,.12)}.wide{width:100%}
.shell{display:grid;grid-template-columns:254px minmax(0,1fr);min-height:100vh;position:relative}
.sidebar{background:rgba(8,11,16,.82);border-right:1px solid var(--line);padding:22px 14px;position:sticky;top:0;height:100vh;backdrop-filter:blur(24px);z-index:20}
.logo{font-size:16px;font-weight:760;letter-spacing:.04em;padding:7px 10px 22px;display:flex;align-items:center;gap:10px}.logo:before{content:"";width:26px;height:26px;border-radius:8px;background:linear-gradient(145deg,#9bddff,#4b91e9);box-shadow:0 0 26px rgba(82,164,255,.28);display:block;clip-path:polygon(18% 18%,82% 18%,82% 82%,54% 82%,54% 52%,18% 52%)}
.workspace{margin:0 5px 22px;padding:12px 13px;border:1px solid var(--line);border-radius:13px;background:rgba(18,24,33,.62)}.workspace small{color:var(--muted2);font-size:11px}.workspace div{margin-top:2px;font-weight:650;color:#dbe7f6;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.nav{display:grid;gap:4px}.nav button{display:flex;align-items:center;gap:11px;text-align:left;padding:10px 12px;border-radius:11px;width:100%;font-weight:590}.nav button svg{width:17px;height:17px;stroke:currentColor;opacity:.82}.nav button.active,.nav button:hover{background:rgba(105,168,236,.09);color:#eaf5ff}.nav button.active{box-shadow:inset 2px 0 0 var(--brand);background:linear-gradient(90deg,rgba(71,145,221,.14),rgba(71,145,221,.035))}
.side-bottom{position:absolute;left:14px;right:14px;bottom:16px}.userbox{padding:12px 10px;border-top:1px solid var(--line);color:#d4deec}.userbox small{color:var(--muted2)}
main{padding:0 38px 70px;max-width:1560px;width:100%;margin:0 auto}.topbar{position:sticky;top:0;z-index:15;display:flex;justify-content:space-between;align-items:center;margin:0 -8px 28px;padding:23px 8px 18px;background:linear-gradient(180deg,rgba(7,9,13,.96) 58%,rgba(7,9,13,0));backdrop-filter:blur(10px)}.topbar h1{font-size:25px;letter-spacing:-.025em;margin:0;font-weight:720}.topbar .muted{font-size:12px;margin-top:2px}
.grid{display:grid;gap:16px}.stats{grid-template-columns:repeat(5,minmax(130px,1fr))}.stat,.card,.tech-card{background:linear-gradient(180deg,rgba(17,22,30,.88),rgba(12,16,22,.88));border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--glow);backdrop-filter:blur(16px)}.stat,.card{padding:20px}.stat{min-height:116px;position:relative;overflow:hidden}.stat:after{content:"";position:absolute;inset:auto -35px -50px auto;width:105px;height:105px;border:1px solid rgba(113,183,255,.08);border-radius:50%}.stat .num{font-size:32px;font-weight:730;letter-spacing:-.035em;margin-top:8px}.stat .muted{font-size:12px}
.card h2,.tech-card h2{font-size:16px;margin:0 0 12px;letter-spacing:-.01em}.toolbar{display:flex;gap:12px;justify-content:space-between;align-items:center;margin-bottom:18px}.actions{display:flex;gap:8px;flex-wrap:wrap}.split{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.table-wrap{overflow:auto;border:1px solid rgba(151,176,214,.08);border-radius:14px}.table{width:100%;border-collapse:collapse}.table th,.table td{text-align:left;border-bottom:1px solid rgba(151,176,214,.08);padding:13px 12px;vertical-align:middle}.table tr:last-child td{border-bottom:0}.table tbody tr{transition:background .14s}.table tbody tr:hover{background:rgba(113,183,255,.025)}.table th{color:#68768a;font-size:11px;text-transform:uppercase;letter-spacing:.06em;font-weight:650}
.badge{display:inline-flex;align-items:center;gap:5px;padding:4px 9px;border-radius:999px;font-size:10px;font-weight:720;letter-spacing:.03em;background:#171f2a;color:#a9b5c6;border:1px solid rgba(255,255,255,.04)}.badge.succeeded,.badge.ready,.badge.active{background:rgba(66,190,145,.08);color:#77dfb8;border-color:rgba(99,214,173,.14)}.badge.failed,.badge.canceled,.badge.expired,.badge.blocked{background:rgba(255,91,116,.08);color:#ff899e;border-color:rgba(255,115,140,.14)}.badge.running,.badge.queued{background:rgba(81,151,230,.09);color:#8bc7ff;border-color:rgba(113,183,255,.14)}
.empty{padding:54px 28px;text-align:center;color:#657388;border:1px dashed rgba(151,176,214,.15);border-radius:16px;background:rgba(12,16,22,.4)}
.modal-backdrop{position:fixed;inset:0;background:rgba(0,0,0,.72);display:grid;place-items:center;z-index:100;padding:24px;backdrop-filter:blur(12px)}.modal{width:min(720px,100%);max-height:91vh;overflow:auto;background:linear-gradient(180deg,#111722,#0d1219);border:1px solid rgba(151,176,214,.17);border-radius:22px;padding:24px;box-shadow:0 38px 120px rgba(0,0,0,.68)}.modal::-webkit-scrollbar{width:8px}.modal::-webkit-scrollbar-thumb{background:#273347;border-radius:8px}.modal-head{display:flex;justify-content:space-between;align-items:flex-start;gap:18px;padding-bottom:14px;border-bottom:1px solid rgba(151,176,214,.09);margin-bottom:17px}.modal-head h2{margin:0;font-size:18px}.iconbtn{border:0;background:transparent;color:#758297;font-size:24px;cursor:pointer}.iconbtn:hover{color:#dce9f8}
.row{display:grid;grid-template-columns:1fr 1fr;gap:14px}.toast{position:fixed;right:24px;bottom:24px;background:#131b26;border:1px solid rgba(113,183,255,.22);box-shadow:var(--shadow);border-radius:13px;padding:12px 16px;z-index:200;color:#dcecff}.progress{height:5px;background:#1d2734;border-radius:9px;overflow:hidden;width:130px}.progress i{display:block;height:100%;background:linear-gradient(90deg,#4b91e9,#72e6ff);box-shadow:0 0 12px rgba(114,230,255,.28)}.code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:#7890ad}.plan-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}.plan{padding:22px;border:1px solid var(--line);border-radius:18px;background:linear-gradient(180deg,rgba(17,23,32,.9),rgba(12,17,24,.84));position:relative}.plan.current{border-color:rgba(113,183,255,.38);box-shadow:0 0 0 1px rgba(113,183,255,.06),0 20px 70px rgba(38,100,170,.11)}.plan .price{font-size:31px;font-weight:730;letter-spacing:-.04em}
.tech-hero{position:relative;overflow:hidden;padding:28px 30px;min-height:168px;border:1px solid rgba(113,183,255,.18);border-radius:22px;background:linear-gradient(115deg,rgba(22,35,52,.9),rgba(10,15,22,.92) 60%,rgba(10,18,28,.9));box-shadow:var(--glow)}.tech-hero:before{content:"";position:absolute;width:330px;height:330px;border-radius:50%;border:1px solid rgba(114,230,255,.11);right:-130px;top:-150px;box-shadow:0 0 80px rgba(58,140,220,.08)}.tech-hero h2{font-size:26px;letter-spacing:-.035em;margin:0 0 8px;position:relative}.tech-hero p{margin:0;color:#91a2b7;max-width:660px;position:relative}.hero-actions{display:flex;gap:10px;margin-top:22px;position:relative}.eyebrow{font-size:10px;text-transform:uppercase;letter-spacing:.16em;color:#6da6da;margin-bottom:8px;font-weight:720}.metric-line{display:flex;gap:26px;align-items:center;flex-wrap:wrap}.metric-line b{font-size:21px}.quota-ring{--p:40;width:108px;height:108px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--brand) calc(var(--p)*1%),#17202b 0);position:relative}.quota-ring:after{content:"";position:absolute;inset:8px;background:#0e141c;border-radius:50%}.quota-ring>div{z-index:1;text-align:center}.quota-ring b{font-size:20px}.quota-ring small{display:block;color:var(--muted2);font-size:10px}
.section-title{display:flex;align-items:end;justify-content:space-between;gap:12px;margin:26px 0 12px}.section-title h2{margin:0;font-size:16px}.section-title p{margin:2px 0 0;color:var(--muted2);font-size:12px}
.course-grid,.asset-grid,.job-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(290px,1fr));gap:14px}.course-card,.asset-card,.job-card{border:1px solid var(--line);border-radius:17px;background:linear-gradient(180deg,rgba(17,22,30,.86),rgba(11,15,21,.84));padding:18px;box-shadow:0 14px 38px rgba(0,0,0,.14);transition:transform .16s,border-color .16s}.course-card:hover,.asset-card:hover,.job-card:hover{transform:translateY(-1px);border-color:rgba(113,183,255,.24)}.course-card h3,.asset-card h3,.job-card h3{margin:0 0 6px;font-size:15px}.course-meta,.asset-meta,.job-meta{display:flex;gap:10px;flex-wrap:wrap;color:#748398;font-size:11px}.course-actions{display:flex;gap:8px;margin-top:18px;padding-top:14px;border-top:1px solid rgba(151,176,214,.07)}
.slide-editor{display:grid;gap:10px;margin-top:12px}.slide-edit-card{border:1px solid rgba(151,176,214,.11);border-radius:14px;padding:14px;background:#0b1017}.slide-edit-card .slide-head{display:flex;justify-content:space-between;gap:10px;align-items:center;margin-bottom:8px}.slide-edit-card .slide-no{font-size:10px;color:#71b7ff;letter-spacing:.08em}.slide-edit-card textarea{min-height:86px}.slide-edit-card select{width:auto;min-width:120px}
.upload-zone{border:1px dashed rgba(113,183,255,.26);border-radius:15px;padding:20px;text-align:center;background:rgba(59,124,188,.035)}.upload-zone input[type=file]{padding:8px;background:transparent;border:0}.status-dot{width:7px;height:7px;border-radius:50%;display:inline-block;background:#738096}.status-dot.good{background:var(--good);box-shadow:0 0 10px rgba(99,214,173,.4)}.status-dot.warn{background:var(--warn)}.status-dot.bad{background:var(--bad)}
.details-box{border:1px solid var(--line);border-radius:13px;padding:13px;background:#0b1017}.details-box summary{cursor:pointer;color:#9aa9bd;font-weight:620}.details-box[open] summary{margin-bottom:10px;color:#c8d7e8}
@media(max-width:1050px){.stats{grid-template-columns:repeat(3,1fr)}.plan-grid{grid-template-columns:1fr}.split{grid-template-columns:1fr}.shell{grid-template-columns:86px minmax(0,1fr)}.sidebar{padding:20px 10px}.logo{font-size:0;justify-content:center}.workspace,.nav span,.side-bottom .userbox{display:none}.nav button{justify-content:center}.nav button svg{width:19px;height:19px}main{padding:0 22px 60px}}
@media(max-width:680px){.auth{padding:14px}.auth-card{grid-template-columns:1fr;min-height:0}.hero{display:none}.formside{padding:34px 24px}.shell{display:block}.sidebar{position:fixed;left:0;right:0;bottom:0;top:auto;width:100%;height:auto;padding:7px 8px;z-index:50;border-right:0;border-top:1px solid var(--line)}.logo,.workspace,.side-bottom{display:none}.nav{grid-template-columns:repeat(7,1fr);gap:2px}.nav button{padding:9px 3px}.nav span{display:none}main{padding:0 14px 84px}.topbar{padding-top:17px;margin-bottom:18px}.topbar h1{font-size:21px}.stats{grid-template-columns:1fr 1fr}.row{grid-template-columns:1fr}.course-grid,.asset-grid,.job-grid{grid-template-columns:1fr}.tech-hero{padding:22px}.metric-line{gap:14px}.modal{padding:18px;border-radius:18px}.hero-actions{flex-wrap:wrap}}
/* Mobile Responsive V2 */
html{-webkit-text-size-adjust:100%;text-size-adjust:100%}
body,.shell{min-height:100dvh}
.sidebar{height:100dvh}
.table-wrap,.slide-strip{-webkit-overflow-scrolling:touch}
@media(max-width:680px){
  body{overscroll-behavior-y:none}
  .shell{min-height:100dvh}
  .sidebar{
    height:auto;
    min-height:0;
    padding:7px 8px calc(7px + env(safe-area-inset-bottom));
    background:rgba(8,11,16,.96);
    backdrop-filter:blur(24px)
  }
  .nav{
    display:flex;
    gap:4px;
    overflow-x:auto;
    overflow-y:hidden;
    scrollbar-width:none;
    scroll-snap-type:x proximity
  }
  .nav::-webkit-scrollbar{display:none}
  .nav button{
    flex:1 0 52px;
    min-width:52px;
    min-height:46px;
    justify-content:center;
    scroll-snap-align:center;
    border-radius:12px
  }
  main{padding:0 12px calc(88px + env(safe-area-inset-bottom))}
  .topbar{
    align-items:flex-start;
    gap:12px;
    margin:0 -2px 16px;
    padding:15px 2px 12px
  }
  .topbar>div{min-width:0}
  .topbar h1{font-size:20px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .topbar .muted{white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:68vw}
  .topbar>button{flex:0 0 auto;min-height:40px;padding:8px 12px}
  .toolbar,.section-title{
    align-items:stretch;
    flex-direction:column;
    gap:10px
  }
  .toolbar .actions,.section-title .actions{width:100%}
  .actions>button{min-height:42px}
  .course-actions{flex-wrap:wrap}
  .course-actions>button{flex:1 1 120px;min-height:42px}
  .card,.stat{padding:16px}
  .modal-backdrop{
    padding:12px 10px calc(12px + env(safe-area-inset-bottom));
    align-items:end
  }
  .modal{
    width:100%;
    max-height:min(88dvh,760px);
    padding:18px;
    border-radius:20px 20px 14px 14px
  }
  .toast{
    left:12px;
    right:12px;
    bottom:calc(82px + env(safe-area-inset-bottom));
    text-align:center
  }
  input,select,textarea{font-size:16px}
  button,.primary,.secondary,.danger{touch-action:manipulation}
}
@media(max-width:420px){
  .stats{grid-template-columns:1fr}
  .stat{min-height:100px}
  .tech-hero{padding:18px}
  .tech-hero h2{font-size:22px}
  .metric-line{align-items:flex-start}
  .section-title h2,.card h2{line-height:1.35}
}

'''


def css_response() -> Response:
    return Response(CSS, media_type="text/css; charset=utf-8")
