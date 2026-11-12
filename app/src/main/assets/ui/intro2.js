/* Заставка «Горы Ирыстона» */
window.OVIntro2 = {
  css: ".intro2 svg * { transform-box: fill-box; transform-origin: 50% 50%; }\n.intro2 .brand { font-family: \"Playfair Display\", Georgia, \"DejaVu Serif\", serif; font-weight: 800; font-size: 31px; fill: #f3f6ff; letter-spacing: .5px; }\n.intro2 .sub { font-family: Georgia, \"DejaVu Serif\", serif; font-size: 13px; letter-spacing: 9px; fill: #f8e2a0; }\n@keyframes n2fadein { from { opacity: 0; } to { opacity: 1; } }\n@keyframes n2fadeout { to { opacity: 0; } }\n@keyframes n2twinkle { 0%, 100% { opacity: .25; } 50% { opacity: 1; } }\n@keyframes n2spin { to { transform: rotate(360deg); } }\n@keyframes n2rise { from { transform: translateY(var(--r, 150px)); opacity: 0; } 55% { opacity: 1; } to { transform: none; opacity: 1; } }\n@keyframes n2sun { from { transform: translateY(190px); } to { transform: none; } }\n@keyframes n2push { from { transform: scale(1); } to { transform: scale(1.07); } }\n@keyframes n2drift { from { transform: translateX(-30px); } to { transform: translateX(30px); } }\n@keyframes n2flow { to { stroke-dashoffset: -72; } }\n@keyframes n2flowS { to { stroke-dashoffset: -44; } }\n@keyframes n2pop { from { opacity: 0; } to { opacity: 1; } }\n@keyframes n2win { from { opacity: 0; } to { opacity: 1; } }\n@keyframes n2smoke { 0% { transform: translate(0, 0) scale(.5); opacity: 0; } 20% { opacity: .55; } 100% { transform: translate(14px, -46px) scale(2.2); opacity: 0; } }\n@keyframes n2fly { from { transform: translate(-60px, 30px); opacity: 0; } 10% { opacity: 1; } 90% { opacity: 1; } to { transform: translate(430px, -50px); opacity: 0; } }\n@keyframes n2flap { 0%, 100% { d: path(\"M0 0 Q5 -7 10 -1 Q15 -7 20 0\"); } 50% { d: path(\"M0 0 Q5 2 10 4 Q15 2 20 0\"); } }\n@keyframes n2glint { 0% { opacity: 0; transform: scale(.2) rotate(0deg); } 40% { opacity: 1; transform: scale(1) rotate(130deg); } 60% { opacity: 1; transform: scale(.92) rotate(200deg); } 85% { opacity: 0; transform: scale(.3) rotate(300deg); } 100% { opacity: 0; transform: scale(.2) rotate(360deg); } }\n@keyframes n2glow { 0%, 100% { opacity: .55; } 50% { opacity: 1; } }\n.intro2 .cam { animation: n2push 9s linear both; transform-origin: 50% 62%; }\n.intro2 .dawn { opacity: 0; animation: n2fadein 4.2s ease-in-out .3s both; }\n.intro2 .star { animation: n2twinkle 2.4s ease-in-out infinite, n2fadeout 2.4s ease-in 1.6s forwards; }\n.intro2 .m1 { --r: 120px; animation: n2rise 2s cubic-bezier(.2,.8,.2,1) .4s both; }\n.intro2 .m2 { --r: 150px; animation: n2rise 2.1s cubic-bezier(.2,.8,.2,1) .7s both; }\n.intro2 .m3 { --r: 220px; animation: n2rise 2.4s cubic-bezier(.2,.8,.2,1) 1s both; }\n.intro2 .m4 { --r: 120px; animation: n2rise 1.9s cubic-bezier(.2,.8,.2,1) 1.6s both; }\n.intro2 .sun { animation: n2sun 3.2s cubic-bezier(.2,.7,.2,1) 1s both; }\n.intro2 .rays { animation: n2spin 40s linear infinite; }\n.intro2 .mist { animation: n2drift 9s ease-in-out infinite alternate, n2fadein 2s ease-out 2.2s both; }\n.intro2 .riv { opacity: 0; animation: n2fadein 1.4s ease-out 2.6s both; }\n.intro2 .wv { fill: none; stroke: #fff; stroke-linecap: round; animation: n2flow 2.6s linear infinite; }\n.intro2 .wvs { fill: none; stroke: #fff; stroke-linecap: round; animation: n2flowS 3.4s linear infinite; }\n.intro2 .home { opacity: 0; animation: n2pop .8s ease-out both; }\n.intro2 .lit { opacity: 0; animation: n2win .9s ease-out both, n2glow 3s ease-in-out infinite; }\n.intro2 .smk { opacity: 0; animation: n2smoke 4.5s ease-out infinite; }\n.intro2 .bird { opacity: 0; animation: n2fly 7s linear infinite; }\n.intro2 .bird path { animation: n2flap .5s ease-in-out infinite; }\n.intro2 .l { opacity: 0; animation: n2pop .8s ease-out both; }\n.intro2 .glint { opacity: 0; animation: n2glint 2.8s ease-in-out infinite both; }\n.intro2 .fade { opacity: 0; animation: n2fadein 1.2s ease-out both; }",
  scene: function () {
  var seed = 7; function rnd() { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; }
  function ridge(pts, rough, depth) {
    var out = [pts[0]];
    for (var i = 1; i < pts.length; i++) {
      var a = pts[i - 1], b = pts[i];
      (function sub(a, b, d, amp) {
        if (d === 0) { out.push(b); return; }
        var mx = (a[0] + b[0]) / 2 + (rnd() - .5) * amp * .5, my = (a[1] + b[1]) / 2 + (rnd() - .5) * amp;
        sub(a, [mx, my], d - 1, amp * .55); sub([mx, my], b, d - 1, amp * .55);
      })(a, b, depth, rough);
    }
    return out;
  }
  function poly(p) { return p.map(function (q) { return q[0].toFixed(1) + "," + q[1].toFixed(1); }).join(" "); }
  function area(p, bottom) { return poly(p.concat([[p[p.length - 1][0], bottom], [p[0][0], bottom]])); }

  var s = '<defs>' +
    '<linearGradient id="night" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#050a1a"/><stop offset="1" stop-color="#17214a"/></linearGradient>' +
    '<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#18204e"/><stop offset=".42" stop-color="#5a427e"/><stop offset=".72" stop-color="#d9788a"/><stop offset="1" stop-color="#f5b36a"/></linearGradient>' +
    '<linearGradient id="rock" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#1f2a58"/><stop offset=".55" stop-color="#55507f"/><stop offset="1" stop-color="#9a7a8c"/></linearGradient>' +
    '<linearGradient id="rockF" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#34437a"/><stop offset="1" stop-color="#7d7396"/></linearGradient>' +
    '<linearGradient id="snow" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#a9bbe4"/><stop offset=".5" stop-color="#eef2ff"/><stop offset="1" stop-color="#ffe6c4"/></linearGradient>' +
    '<linearGradient id="haze" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffb27a" stop-opacity="0"/><stop offset="1" stop-color="#ffb27a" stop-opacity=".45"/></linearGradient>' +
    '<radialGradient id="gsun"><stop offset="0" stop-color="#fff5cc"/><stop offset=".3" stop-color="#ffd37a" stop-opacity=".9"/><stop offset="1" stop-color="#ffb060" stop-opacity="0"/></radialGradient>' +
    '<radialGradient id="gl"><stop offset="0" stop-color="#fff" stop-opacity=".95"/><stop offset=".45" stop-color="#fff3c9" stop-opacity=".3"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>' +
    '<linearGradient id="water" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4fc3c0"/><stop offset="1" stop-color="#156a7e"/></linearGradient>' +
    '<linearGradient id="stone" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#7d7f98"/><stop offset="1" stop-color="#a39a9c"/></linearGradient>' +
    '<linearGradient id="hill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#4b5d45"/><stop offset=".5" stop-color="#2a4038"/><stop offset="1" stop-color="#10202a"/></linearGradient>' +
    '<linearGradient id="hillB" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#2d4a42"/><stop offset="1" stop-color="#5f7a4f"/></linearGradient>' +
    '<radialGradient id="warm"><stop offset="0" stop-color="#ffd27a" stop-opacity=".9"/><stop offset="1" stop-color="#ffd27a" stop-opacity="0"/></radialGradient>' +
    '<filter id="bl"><feGaussianBlur stdDeviation="5"/></filter>' +
    '</defs>';

  s += '<rect width="360" height="640" fill="url(#night)"/><rect class="dawn" width="360" height="640" fill="url(#sky)"/>';
  var i, st = '';
  for (i = 0; i < 70; i++) st += '<circle class="star" cx="' + (rnd() * 360).toFixed(0) + '" cy="' + (rnd() * 260).toFixed(0) + '" r="' + (0.5 + rnd() * 1.2).toFixed(1) + '" fill="#fff" style="animation-delay:' + (rnd() * 2.4).toFixed(1) + 's,' + (1.6 + rnd() * 1.2).toFixed(1) + 's"/>';
  s += '<g class="cam">' + st;

  /* солнце за правым хребтом */
  s += '<g class="sun"><g transform="translate(300,250)"><circle r="150" fill="url(#gsun)"/></g></g>';

  s += '<g transform="translate(0,58)">';
  /* дальний хребет справа */
  var far = ridge([[150, 300], [215, 262], [262, 238], [304, 196], [338, 214], [372, 176], [390, 200]], 10, 2);
  s += '<g class="m1"><clipPath id="cf"><polygon points="' + area(far, 700) + '"/></clipPath>' +
    '<polygon points="' + area(far, 700) + '" fill="#5a527f" opacity=".95"/>' +
    '<g clip-path="url(#cf)"><polygon points="' + poly(ridge([[150, 150], [215, 262], [262, 262], [300, 240], [340, 250], [372, 230], [390, 150]], 8, 2)) + '" fill="#e8ecff" opacity=".9"/></g></g>';

  /* главная пирамида, левая вершина, правая гряда */
  var top = ridge([[-20, 300], [8, 276], [48, 236], [72, 256], [98, 270], [126, 238], [152, 208], [174, 166], [196, 126], [212, 160], [228, 180], [246, 200], [264, 212], [290, 222], [316, 238], [344, 250], [380, 244]], 9, 2);
  var snowLine = ridge([[-20, 318], [30, 296], [64, 318], [100, 304], [134, 340], [168, 300], [196, 356], [224, 304], [252, 336], [282, 306], [320, 334], [380, 312]], 12, 2);
  s += '<g class="m3"><clipPath id="cM"><polygon points="' + area(top, 700) + '"/></clipPath>' +
    '<polygon points="' + area(top, 700) + '" fill="url(#rock)"/>' +
    '<g clip-path="url(#cM)">' +
    '<polygon points="' + poly([[-20, 100]].concat(snowLine, [[380, 100]])) + '" fill="url(#snow)"/>' +
    /* тень левой грани и гребни */
    '<polygon points="196,126 178,170 172,214 158,262 170,330 150,400 40,400 -20,330 -20,100 196,100" fill="#1a2552" opacity=".34"/>' +
    '<polygon points="48,236 36,268 44,300 22,330 -20,336 -20,270" fill="#1a2552" opacity=".3"/>' +
    '<polygon points="196,126 214,166 208,214 226,262 214,330 232,360 300,360 300,200" fill="#ffd9a8" opacity=".14"/>' +
    '<path d="M196 126 L184 168 L190 214 L174 262 L182 320" fill="none" stroke="#1a2552" stroke-width="1.4" opacity=".5"/>' +
    '<path d="M196 126 L208 164 L202 206 L222 252 L214 312" fill="none" stroke="#1a2552" stroke-width="1.2" opacity=".4"/>' +
    '<path d="M174 166 L160 214 L170 262" fill="none" stroke="#1a2552" stroke-width="1" opacity=".4"/>' +
    '<path d="M126 238 L116 280 L128 322" fill="none" stroke="#1a2552" stroke-width="1" opacity=".4"/>' +
    '<path d="M264 212 L258 262 L270 300" fill="none" stroke="#2a2f5e" stroke-width="1" opacity=".35"/>' +
    '<polygon points="172,214 158,262 140,284 168,296 182,262" fill="#4a4a7c" opacity=".7"/>' +
    '<polygon points="208,214 226,262 244,276 222,300 212,262" fill="#7a6a88" opacity=".55"/>' +
    '<polygon points="120,246 108,284 128,300 138,270" fill="#4a4a7c" opacity=".55"/>' +
    '<polygon points="262,214 252,252 276,270 290,240" fill="#8a7890" opacity=".5"/>' +
    '<polygon points="196,126 184,168 190,214 178,236 196,230 204,186" fill="#2a3566" opacity=".28"/>' +
    '<polygon points="196,230 178,236 174,262 196,274 210,252" fill="#c8d2f2" opacity=".5"/>' +
    '<polygon points="48,236 60,262 76,262 70,300 50,296 40,262" fill="#c9d4f4" opacity=".5"/>' +
    /* ледник слева */
    '<polygon points="64,318 82,372 100,340 118,382 134,340 100,304" fill="#dbe4fb" opacity=".85"/>' +
    '<polygon points="230,306 244,368 262,336 280,372 290,310 252,336" fill="#e6ecff" opacity=".8"/>' +
    /* осыпи под снегом */
    '<polygon points="-20,400 40,372 100,396 160,380 196,404 250,378 320,396 380,372 380,460 -20,460" fill="#3a3a68" opacity=".55"/>' +
    '</g></g>';

  /* дымка */
  s += '<rect y="390" width="360" height="90" fill="url(#haze)"/>';
  s += '<g class="mist" filter="url(#bl)"><ellipse cx="110" cy="418" rx="130" ry="12" fill="#ffd9c0" opacity=".28"/><ellipse cx="270" cy="436" rx="110" ry="10" fill="#ffd9c0" opacity=".22"/></g>';

  /* деревня и башни */
  function win(x, y, w, h, d, hd) { return '<g class="home" style="animation-delay:' + hd + 's"><rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" fill="#2a2a3c"/><g class="lit" style="animation-delay:' + d + 's,' + d + 's"><circle cx="' + (x + w / 2) + '" cy="' + (y + h / 2) + '" r="' + (Math.max(w, 2.4) * 2.4) + '" fill="url(#warm)"/><rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '" fill="#ffd27a"/></g></g>'; }
  function stones(x, y, w, h) { var o = ''; for (var k = 1; k < Math.floor(h / 4.5); k++) o += '<line x1="' + x + '" y1="' + (y + k * 4.5) + '" x2="' + (x + w) + '" y2="' + (y + k * 4.5) + '" stroke="#3b3e56" stroke-width=".5" opacity=".55"/>'; return o; }
  function house(x, y, w, h, d) {
    return '<g class="home" style="animation-delay:' + d + 's"><rect x="' + x + '" y="' + y + '" width="' + w + '" height="' + (h + 40) + '" fill="url(#stone)"/>' + stones(x, y, w, h) +
      '<rect x="' + (x - 1.5) + '" y="' + (y - 3) + '" width="' + (w + 3) + '" height="3.5" fill="#3a3d58"/>' +
      '<rect x="' + (x + w * .12) + '" y="' + (y + h * .4) + '" width="' + (w * .2) + '" height="' + (h * .3) + '" fill="#2a2a3c"/></g>' +
      win(x + w * .58, y + h * .3, w * .16, h * .26, d + 0.9, d);
  }
  function towerF(x, y, w, h, d, sm) { // каменная башня с зубцами
    var m = '', n = 3, k;
    for (k = 0; k < n; k++) m += '<rect x="' + (x - 1 + k * (w + 2 - w * .26) / (n - 1)) + '" y="' + (y - 9) + '" width="' + (w * .26) + '" height="4.5" fill="#4a4d6b"/>';
    var ws = '';
    var nw = Math.max(1, Math.floor(h / 32));
    for (k = 0; k < nw; k++) ws += win(x + w * .42, y + h * (k + .5) / nw - 4, w * .14, 8, d + 1 + k * .3, d);
    return '<g class="home" style="animation-delay:' + d + 's"><polygon points="' + (x - 1) + ',' + (y + h + 40) + ' ' + (x + w + 1) + ',' + (y + h + 40) + ' ' + (x + w - 1) + ',' + y + ' ' + (x + 1) + ',' + y + '" fill="url(#stone)"/>' + stones(x + 1, y, w - 2, h) +
      '<polygon points="' + (x + w * .55) + ',' + y + ' ' + (x + w - 1) + ',' + y + ' ' + (x + w + 1) + ',' + (y + h + 40) + ' ' + (x + w * .55) + ',' + (y + h + 40) + '" fill="#ffd9a8" opacity=".14"/>' +
      '<rect x="' + (x - 2.5) + '" y="' + (y - 5) + '" width="' + (w + 5) + '" height="5.5" fill="#34374f"/>' + m + '</g>' + ws +
      (sm ? '<circle class="smk" cx="' + (x + w * .5) + '" cy="' + (y - 11) + '" r="3" fill="#cfd3e6" style="animation-delay:' + (d + 2) + 's"/>' : '');
  }
  function tower(x, y, w, h, d) { // башня со ступенчатой кровлей
    var r = '', steps = 4, i2;
    for (i2 = 0; i2 < steps; i2++) { var ww = w * (1 - i2 * .2), hh = 3.8; r += '<rect x="' + (x + (w - ww) / 2) + '" y="' + (y - (i2 + 1) * hh) + '" width="' + ww + '" height="' + hh + '" fill="' + (i2 % 2 ? '#4a4d6b' : '#3a3d58') + '"/>'; }
    r += '<polygon points="' + (x + w * .5) + ',' + (y - steps * 3.8 - 6) + ' ' + (x + w * .38) + ',' + (y - steps * 3.8) + ' ' + (x + w * .62) + ',' + (y - steps * 3.8) + '" fill="#2f3250"/>';
    return '<g class="home" style="animation-delay:' + d + 's"><polygon points="' + x + ',' + (y + h + 40) + ' ' + (x + w) + ',' + (y + h + 40) + ' ' + (x + w * .94) + ',' + y + ' ' + (x + w * .06) + ',' + y + '" fill="url(#stone)"/>' + stones(x + w * .06, y, w * .88, h) + r + '</g>' +
      win(x + w * .4, y + h * .22, w * .16, 7, d + 1.1, d);
  }
  var v = '';
  v += tower(150, 402, 14, 24, 3.1) + towerF(78, 410, 14, 32, 3.2, false) + towerF(252, 408, 13, 34, 3.4, false);
  v += house(106, 432, 30, 16, 3.0) + house(140, 424, 36, 24, 3.2) + house(204, 432, 26, 16, 3.4) + house(232, 436, 18, 12, 3.6);
  v += house(54, 438, 22, 12, 3.8) + house(8, 444, 30, 14, 4.0) + house(272, 436, 20, 12, 4.1) + house(30, 436, 20, 10, 4.3);
  v += towerF(298, 352, 22, 92, 2.8, true) + house(324, 428, 28, 16, 4.2);
  s += '<g>' + v + '</g>';
  /* основной склон */
  var hl = ridge([[-20, 472], [14, 458], [56, 451], [104, 449], [158, 447], [210, 449], [252, 449], [292, 449], [336, 446], [380, 442]], 3, 2);
  var strata = '';
  for (i = 0; i < 9; i++) { var yy = 470 + i * 12 + rnd() * 5, x0 = rnd() * 220; strata += '<path d="M' + x0.toFixed(0) + ' ' + yy.toFixed(0) + ' q40 -' + (2 + rnd() * 5).toFixed(0) + ' ' + (70 + rnd() * 90).toFixed(0) + ' ' + (rnd() * 8 - 2).toFixed(0) + '" fill="none" stroke="#14202a" stroke-width="1.1" opacity=".45"/>'; }
  s += '<g class="m4"><clipPath id="ch"><polygon points="' + area(hl, 700) + '"/></clipPath><polygon points="' + area(hl, 700) + '" fill="url(#hill)"/>' +
    '<g clip-path="url(#ch)">' + strata + '<polygon points="-20,520 60,500 120,540 80,640 -20,640" fill="#0f1a24" opacity=".4"/><polygon points="250,470 330,456 380,470 380,560 290,540" fill="#ffd9a8" opacity=".08"/></g></g>';


  /* деревья на склоне */
  function tree(x, y, r, d, c) { return '<g class="home" style="animation-delay:' + d + 's"><circle cx="' + x + '" cy="' + y + '" r="' + r + '" fill="' + c + '"/><circle cx="' + (x + r * .35) + '" cy="' + (y - r * .3) + '" r="' + (r * .6) + '" fill="#4a6a46" opacity=".55"/></g>'; }
  function pine(x, y, h, d) { return '<g class="home" style="animation-delay:' + d + 's"><polygon points="' + x + ',' + (y - h) + ' ' + (x - h * .24) + ',' + (y - h * .35) + ' ' + (x + h * .24) + ',' + (y - h * .35) + '" fill="#0d1a2c"/><polygon points="' + x + ',' + (y - h * .75) + ' ' + (x - h * .3) + ',' + (y - h * .1) + ' ' + (x + h * .3) + ',' + (y - h * .1) + '" fill="#0a1424"/></g>'; }
  var t = '';
  [[248, 560, 16], [270, 576, 20], [296, 566, 18], [322, 580, 22], [346, 566, 18], [236, 590, 14], [284, 596, 16], [330, 604, 18]].forEach(function (p, k) { t += tree(p[0], p[1], p[2], 3.4 + k * .1, k % 2 ? '#1d3a2c' : '#25452f'); });
  [[24, 540, 40], [44, 552, 32], [68, 548, 26], [92, 560, 22], [12, 580, 34]].forEach(function (p, k) { t += pine(p[0], p[1], p[2], 3.3 + k * .1); });
  [].forEach(function (p, k) { t += tree(p[0], p[1], p[2], 3.2 + k * .1, '#2a4a35'); });
  s += t;

  s += '</g>';
  /* река с изгибами и белыми волнами */
  var CL = [[190, 506, 4], [192, 524, 10], [178, 550, 20], [156, 582, 36], [150, 616, 58], [118, 650, 92], [60, 690, 150]];
  var Lp = CL.map(function (c) { return [c[0] - c[2] / 2, c[1]]; }), Rp = CL.map(function (c) { return [c[0] + c[2] / 2, c[1]]; });
  function sm(P) { var d = 'M' + P[0][0].toFixed(1) + ' ' + P[0][1].toFixed(1); for (var j = 0; j < P.length - 1; j++) { var p0 = P[j - 1] || P[j], p1 = P[j], p2 = P[j + 1], p3 = P[j + 2] || p2; d += ' C' + (p1[0] + (p2[0] - p0[0]) / 6).toFixed(1) + ' ' + (p1[1] + (p2[1] - p0[1]) / 6).toFixed(1) + ', ' + (p2[0] - (p3[0] - p1[0]) / 6).toFixed(1) + ' ' + (p2[1] - (p3[1] - p1[1]) / 6).toFixed(1) + ', ' + p2[0].toFixed(1) + ' ' + p2[1].toFixed(1); } return d; }
  function smTail(P) { return sm(P).replace(/^M[^C]*/, ''); }
  var Rrev = Rp.slice().reverse();
  s += '<g class="riv"><path d="' + sm(Lp) + ' L' + Rp[Rp.length - 1][0] + ' ' + Rp[Rp.length - 1][1] + ' ' + smTail(Rrev) + 'Z" fill="url(#water)"/>';
  s += '<path d="' + sm(Lp) + '" fill="none" stroke="#bfeee9" stroke-width="1.3" opacity=".6"/><path d="' + sm(Rp) + '" fill="none" stroke="#bfeee9" stroke-width="1.3" opacity=".6"/>';
  function fr(f) { return Lp.map(function (a, j) { return [a[0] + (Rp[j][0] - a[0]) * f, a[1]]; }); }
  [.18, .34, .5, .66, .82].forEach(function (f, k) {
    s += '<path class="wv" d="' + sm(fr(f)) + '" stroke-width="' + (1 + f * 1.4).toFixed(1) + '" opacity="' + (0.55 + (k % 2) * .2) + '" stroke-dasharray="' + (10 + k * 2) + ' ' + (20 - k) + '" style="animation-delay:' + (-k * .55).toFixed(2) + 's"/>';
  });
  [.08, .42, .75, .92].forEach(function (f, k) {
    s += '<path class="wvs" d="' + sm(fr(f)) + '" stroke-width="1.1" opacity=".45" stroke-dasharray="5 17" style="animation-delay:' + (-k * .7).toFixed(2) + 's"/>';
  });
  s += '</g>';

  /* передний план */
  s += '<polygon points="' + area(ridge([[-10, 616], [50, 600], [110, 634], [140, 668]], 8, 2), 680) + '" fill="#070d1d"/><polygon points="' + area(ridge([[222, 680], [270, 640], [330, 610], [370, 618]], 8, 2), 690) + '" fill="#070d1d"/>';

  /* птицы */
  [[0, 130, 4.0], [26, 156, 4.4], [-18, 172, 4.9]].forEach(function (b) { s += '<g class="bird" transform="translate(' + b[0] + ',' + b[1] + ')" style="animation-delay:' + b[2] + 's"><path d="M0 0 Q5 -7 10 -1 Q15 -7 20 0" fill="none" stroke="#0e1535" stroke-width="1.8" stroke-linecap="round"/></g>'; });

  /* блик на вершине */
  s += '<g transform="translate(196,184)"><g class="glint" style="animation-delay:4.6s"><circle r="17" fill="url(#gl)"/><path d="M0,-21 Q1.8,-1.8 21,0 Q1.8,1.8 0,21 Q-1.8,1.8 -21,0 Q-1.8,-1.8 0,-21Z" fill="#fff"/></g></g>';
  s += '</g>';

  /* заголовок */
  var title = 'Ossetian VPN', tx = '<text class="brand" x="180" y="78" text-anchor="middle">';
  for (i = 0; i < title.length; i++) tx += '<tspan class="l" style="animation-delay:' + (3.7 + i * .08).toFixed(2) + 's">' + (title[i] === ' ' ? ' ' : title[i]) + '</tspan>';
  tx += '</text>';
  s += '<text class="sub fade" x="180" y="46" text-anchor="middle" style="animation-delay:3.4s">ИРЫСТОН</text>' + tx;
  return s.replace(/id="(\w+)"/g, 'id="n2$1"').replace(/url\(#(\w+)\)/g, 'url(#n2$1)');
}
};
