/* =============================================================================
 * scene.js — 電影感 3D 模型場景（霓虹 bloom + 資料封包通訊）
 * 節點 = 真正的 3D 模型（代理人核心+光環 / AI 腦 / 資料庫圓柱 / 伺服器方塊）
 * 通訊 = 跑 Pipeline 時，帶訊息的資料封包沿光束在節點間飛行 → 看得到流程溝通
 * 互動 = 拖曳旋轉 / 滾輪縮放 / 點節點開 demo / 相機聚焦
 * ========================================================================== */
(function (global) {
  "use strict";
  const L = global.LOBSTER;
  const T = global.THREE;

  let renderer, scene, camera, raycaster, clock, composer, bloomPass;
  let starField;
  const nodeObjs = {};   // id -> { group, core, wire, glow, label, color, basePos, kind, spin, pulse }
  const pickables = [];  // 可被點擊 raycast 的物件（核心/輝光/標籤）
  const mixers = [];     // 載入的 glTF 模型動畫 AnimationMixer
  const beams = [];      // { curve, tube, from, to, color }
  const curves = {};     // "from>to" -> curve
  const packets = [];    // 飛行中的封包
  const pointer = new T.Vector2();
  const plots = [];      // 各節點地塊（社區地基）
  let groundGrid = null, groundDisc = null;
  let frozen = false, _frozenT = 0;  // 暫停查看：凍結時間動畫，但相機仍可轉
  let hovered = null, paused = false, useBloom = false, themeLight = false;

  const cam = {
    target: new T.Vector3(0, 0.8, 1),
    radius: 40, theta: -0.42, phi: 0.92, velTheta: 0, velPhi: 0,
    autoRotate: true, idleTimer: 0,
    focusing: false, focusTarget: null, focusRadius: 40, toTheta: -0.42, toPhi: 0.92, mode: "free",
  };
  let dragging = false, panning = false, downX = 0, downY = 0, moved = 0, lastX = 0, lastY = 0;
  const cbHover = [], cbClick = [];

  function fitRadius(factor) {
    const aspect = window.innerWidth / window.innerHeight;
    const tanV = Math.tan((52 * Math.PI) / 360);
    // 半範圍：村落攤平後較寬，要框得下整個社區
    const r = Math.max(19 / tanV, 18 / (aspect * tanV));
    return Math.max(26, Math.min(82, r * (factor || 1)));
  }

  /* 節點造型分類 */
  const KIND = {
    user: "screen", app: "screen",
    collector: "core", analyst: "core", advisor: "core",
    epa: "box", openmeteo: "box", civic: "box",
    rag: "orb", llm: "orb",
    sqlite: "db", export: "export", hermes: "bot", discord: "chat",
  };

  /* =======================================================================
   * 初始化
   * ==================================================================== */
  function init() {
    const canvas = document.getElementById("scene");
    renderer = new T.WebGLRenderer({ canvas, antialias: true, alpha: false });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.setSize(window.innerWidth, window.innerHeight);

    scene = new T.Scene();
    scene.background = new T.Color(0x04060f);
    scene.fog = new T.FogExp2(0x04060f, 0.011);

    camera = new T.PerspectiveCamera(52, window.innerWidth / window.innerHeight, 0.1, 320);
    raycaster = new T.Raycaster();
    clock = new T.Clock();
    cam.radius = cam.focusRadius = fitRadius();

    scene.add(new T.AmbientLight(0x6688cc, 0.7));
    const d1 = new T.DirectionalLight(0xffffff, 0.8); d1.position.set(6, 14, 10); scene.add(d1);
    const d2 = new T.DirectionalLight(0x00d9ff, 0.4); d2.position.set(-12, -4, -8); scene.add(d2);

    setupBloom();
    buildStars();
    buildGround();
    buildBeams();
    buildNodes();
    buildRegions();
    updateCamera();
    bindEvents();
    animate();
  }

  function setupBloom() {
    if (global.LOBSTER_NOBLOOM || !T.EffectComposer || !T.UnrealBloomPass) { useBloom = false; return; }
    try {
      composer = new T.EffectComposer(renderer);
      composer.addPass(new T.RenderPass(scene, camera));
      bloomPass = new T.UnrealBloomPass(
        new T.Vector2(window.innerWidth, window.innerHeight), 0.95, 0.5, 0.62
      );
      composer.addPass(bloomPass);
      composer.setSize(window.innerWidth, window.innerHeight);
      useBloom = true;
    } catch (e) { useBloom = false; }
  }

  /* ── 星空 ───────────────────────────────────────────── */
  function buildStars() {
    const N = 1500, g = new T.BufferGeometry(), pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const r = 70 + Math.random() * 140;
      const a = Math.random() * Math.PI * 2, b = Math.acos(Math.random() * 2 - 1);
      pos[i * 3] = r * Math.sin(b) * Math.cos(a);
      pos[i * 3 + 1] = r * Math.sin(b) * Math.sin(a);
      pos[i * 3 + 2] = r * Math.cos(b);
    }
    g.setAttribute("position", new T.BufferAttribute(pos, 3));
    starField = new T.Points(g, new T.PointsMaterial({ color: 0x44557a, size: 0.7, transparent: true, opacity: 0.8 }));
    scene.add(starField);
  }

  /* ── 社區地面（地坪圓盤 + 街道格線）──────────────────── */
  function buildGround() {
    groundDisc = new T.Mesh(new T.CircleGeometry(52, 64),
      new T.MeshBasicMaterial({ color: 0x0a1426, transparent: true, opacity: 0.55, depthWrite: false }));
    groundDisc.rotation.x = -Math.PI / 2; groundDisc.position.y = -0.06; scene.add(groundDisc);
    groundGrid = new T.GridHelper(104, 52, 0x214066, 0x122339);
    groundGrid.position.y = -0.02;
    groundGrid.material.transparent = true; groundGrid.material.opacity = 0.5;
    scene.add(groundGrid);
  }

  /* =======================================================================
   * 3D 節點模型
   * ==================================================================== */
  function colHex(c) { return new T.Color(c); }

  function buildNodes() {
    L.NODES.forEach((node) => {
      const kind = KIND[node.id] || "box";
      const group = new T.Group();
      group.position.set(node.pos[0], node.pos[1], node.pos[2]);
      const col = colHex(node.color);
      // 霓虹全息風：半透明面 + 亮線框 + 輝光（MeshBasic，弱 GPU 也跑得動）
      const faceMat = (o) => new T.MeshBasicMaterial({ color: col, transparent: true, opacity: o == null ? 0.4 : o, depthWrite: false });
      const lineMat = (o) => new T.LineBasicMaterial({ color: col, transparent: true, opacity: o == null ? 0.45 : o });
      const addMat = (o) => new T.MeshBasicMaterial({ color: col, transparent: true, opacity: o == null ? 0.85 : o, blending: T.AdditiveBlending, depthWrite: false });
      const solid = () => new T.MeshBasicMaterial({ color: col });
      const wireG = (g, o) => new T.LineSegments(new T.WireframeGeometry(g), lineMat(o));
      const baseRing = (rad) => { const t = new T.Mesh(new T.TorusGeometry(rad, 0.05, 6, 30), addMat(0.55)); t.rotation.x = Math.PI / 2; t.position.y = -1.55; return t; };
      const orbiters = (n, rad, sz) => { const g = new T.Group(); for (let i = 0; i < n; i++) { const a = i / n * 6.283; const m = new T.Mesh(new T.OctahedronGeometry(sz, 0), solid()); m.position.set(Math.cos(a) * rad, (i % 2 ? 0.14 : -0.14), Math.sin(a) * rad); g.add(m); } return g; };

      let core, wire = null, spin = { y: 0.3, ring: 0.5 };
      const ring = new T.Group();
      const statics = [];

      if (kind === "core") {
        // 代理人：八面體核心 + 旋轉光環
        core = new T.Mesh(new T.IcosahedronGeometry(1.0, 1), faceMat(0.32));
        core.add(new T.Mesh(new T.OctahedronGeometry(0.5, 0), solid()));   // 內能量核
        wire = wireG(new T.IcosahedronGeometry(1.15, 1), 0.5);
        const t1 = new T.Mesh(new T.TorusGeometry(1.8, 0.05, 6, 36), addMat(0.8)); t1.rotation.x = Math.PI / 2; ring.add(t1);
        const t2 = new T.Mesh(new T.TorusGeometry(1.38, 0.04, 6, 30), addMat(0.7)); t2.rotation.set(Math.PI / 2.3, 0.5, 0); ring.add(t2);
        ring.add(orbiters(8, 2.0, 0.09));   // 軌道資料節點
        statics.push(baseRing(1.55));
        spin = { y: 0.35, ring: 0.55 };
      } else if (kind === "orb") {
        // RAG / LLM：發光線框球（AI 腦）
        core = new T.Mesh(new T.IcosahedronGeometry(1.0, 1), faceMat(0.14));
        core.add(new T.Mesh(new T.IcosahedronGeometry(0.42, 0), solid()));
        wire = wireG(new T.IcosahedronGeometry(1.12, 2), 0.4);            // 巢狀腦線框
        ring.add(wireG(new T.IcosahedronGeometry(0.72, 1), 0.55));
        ring.add(orbiters(6, 1.45, 0.07));                                // 軌道突觸
        spin = { y: 0.5, ring: -0.7 };
      } else if (kind === "db") {
        // SQLite：堆疊圓柱（資料庫磁碟）
        core = new T.Group();
        for (let i = 0; i < 4; i++) {
          const disk = new T.Mesh(new T.CylinderGeometry(0.95, 0.95, 0.26, 18), faceMat(0.42));
          disk.position.y = (i - 1.5) * 0.42; core.add(disk);
          const rim = new T.Mesh(new T.TorusGeometry(0.95, 0.035, 6, 24), addMat(0.9));
          rim.rotation.x = Math.PI / 2; rim.position.y = (i - 1.5) * 0.42 + 0.13; core.add(rim);
        }
        for (let k = 0; k < 3; k++) { const a = k / 3 * 6.283; const rod = new T.Mesh(new T.CylinderGeometry(0.04, 0.04, 1.9, 6), addMat(0.5)); rod.position.set(Math.cos(a) * 0.95, 0, Math.sin(a) * 0.95); core.add(rod); }
        ring.add(orbiters(5, 1.3, 0.06));   // 軌道資料位
        statics.push(baseRing(1.1));
        spin = { y: 0.22, ring: 0.5 };
      } else if (kind === "screen") {
        // 使用者 / App：螢幕面板
        core = new T.Mesh(new T.BoxGeometry(2.2, 1.4, 0.12), faceMat(0.38));
        wire = wireG(new T.BoxGeometry(2.32, 1.52, 0.18), 0.5);
        const pts = []; for (let i = 0; i < 4; i++) { const y = 0.42 - i * 0.26; pts.push(-0.85, y, 0.08, 0.55 + (i % 2) * 0.25, y, 0.08); }
        const lg = new T.BufferGeometry(); lg.setAttribute("position", new T.Float32BufferAttribute(pts, 3));
        core.add(new T.LineSegments(lg, lineMat(0.6)));                   // 螢幕內容線條
        const stand = new T.Mesh(new T.BoxGeometry(0.22, 0.5, 0.1), faceMat(0.5)); stand.position.y = -0.95; statics.push(stand);
        const sbase = new T.Mesh(new T.BoxGeometry(0.9, 0.08, 0.5), faceMat(0.5)); sbase.position.y = -1.22; statics.push(sbase);
        spin = { y: 0, ring: 0 };
      } else if (kind === "bot") {
        // Agent Bot:機器人頭 + 兩側翼 + 天線 + 光環(對接外部聊天的 agent)
        core = new T.Mesh(new T.IcosahedronGeometry(0.85, 1), faceMat(0.34));
        core.add(new T.Mesh(new T.OctahedronGeometry(0.4, 0), solid()));               // 內核(眼)
        wire = wireG(new T.IcosahedronGeometry(0.98, 1), 0.5);
        [-1, 1].forEach((s) => {                                                          // 兩側翼
          const w = new T.Mesh(new T.PlaneGeometry(0.9, 0.55), addMat(0.5));
          w.position.set(s * 1.05, 0.1, 0); w.rotation.y = s * 0.5; w.material.side = T.DoubleSide; core.add(w);
        });
        const ant = new T.Mesh(new T.CylinderGeometry(0.025, 0.025, 0.55, 6), addMat(0.7)); ant.position.y = 1.0; core.add(ant);
        const tip = new T.Mesh(new T.OctahedronGeometry(0.1, 0), solid()); tip.position.y = 1.32; core.add(tip);  // 天線
        const tb = new T.Mesh(new T.TorusGeometry(1.5, 0.045, 6, 32), addMat(0.7)); tb.rotation.x = Math.PI / 2; ring.add(tb);
        statics.push(baseRing(1.25));
        spin = { y: 0.3, ring: 0.5 };
      } else if (kind === "chat") {
        // 聊天平台:對話泡泡 + 打字三點 + 泡泡尾巴
        core = new T.Mesh(new T.BoxGeometry(1.5, 1.05, 0.4), faceMat(0.36));
        wire = wireG(new T.BoxGeometry(1.6, 1.15, 0.48), 0.5);
        for (let i = 0; i < 3; i++) { const dot = new T.Mesh(new T.SphereGeometry(0.12, 10, 10), solid()); dot.position.set((i - 1) * 0.35, 0, 0.22); core.add(dot); }
        const tail = new T.Mesh(new T.ConeGeometry(0.22, 0.42, 4), faceMat(0.36)); tail.position.set(-0.45, -0.62, 0); tail.rotation.z = 0.5; core.add(tail);
        ring.add(orbiters(4, 1.3, 0.06));
        spin = { y: 0.25, ring: 0.42 };
      } else if (kind === "export") {
        // 資料匯出:JSON 文件卡 + 內文線 + 向外箭頭(latest_aqi.json)
        core = new T.Mesh(new T.BoxGeometry(1.2, 1.5, 0.12), faceMat(0.4));
        wire = wireG(new T.BoxGeometry(1.3, 1.6, 0.2), 0.5);
        for (let i = 0; i < 4; i++) { const ln = new T.Mesh(new T.BoxGeometry(0.8, 0.07, 0.02), addMat(0.6)); ln.position.set(-0.05, 0.45 - i * 0.28, 0.08); core.add(ln); }
        const shaft = new T.Mesh(new T.CylinderGeometry(0.06, 0.06, 0.5, 8), addMat(0.7)); shaft.position.set(0.62, 0, 0.2); shaft.rotation.z = Math.PI / 2; core.add(shaft);
        const arrow = new T.Mesh(new T.ConeGeometry(0.2, 0.42, 12), solid()); arrow.position.set(1.0, 0, 0.2); arrow.rotation.z = -Math.PI / 2; core.add(arrow);  // 向外匯出
        statics.push(baseRing(1.1));
        spin = { y: 0, ring: 0.4 };
      } else {
        // 資料源 / 服務：伺服器方塊
        core = new T.Mesh(new T.BoxGeometry(1.5, 1.5, 1.5), faceMat(0.34));
        core.add(new T.Mesh(new T.OctahedronGeometry(0.35, 0), solid()));
        wire = wireG(new T.BoxGeometry(1.64, 1.64, 1.64), 0.5);
        for (let i = 0; i < 3; i++) {
          const y = 0.45 - i * 0.45;
          const u = new T.Mesh(new T.BoxGeometry(1.25, 0.1, 0.04), addMat(0.5)); u.position.set(0, y, 0.77); core.add(u);  // 機架單元
          const led = new T.Mesh(new T.OctahedronGeometry(0.06, 0), solid()); led.position.set(0.48, y, 0.8); core.add(led); // 狀態 LED
        }
        if (node.id === "civic") {
          const ant = new T.Mesh(new T.CylinderGeometry(0.02, 0.02, 0.7, 6), addMat(0.7)); ant.position.y = 1.12; core.add(ant);
          const tip = new T.Mesh(new T.OctahedronGeometry(0.1, 0), solid()); tip.position.y = 1.52; core.add(tip);          // 感測器天線
        }
        spin = { y: 0.28, ring: 0 };
      }
      if (wire && global.LOBSTER_NOWIRE) wire = null; // 測試用：略過線框
      group.add(core);
      if (wire) group.add(wire);
      group.add(ring);
      statics.forEach((s) => group.add(s));

      // 輝光
      const glow = new T.Sprite(new T.SpriteMaterial({ map: glowTex(node.color), transparent: true, blending: T.AdditiveBlending, depthWrite: false, opacity: 0.85 }));
      glow.scale.set(7, 7, 1); group.add(glow);

      // 標籤（billboard）
      const label = new T.Sprite(new T.SpriteMaterial({ map: labelTex(node), transparent: true, depthWrite: false, depthTest: false }));
      label.scale.set(4.4, 1.45, 1); label.position.y = 2.6; label.renderOrder = 10; group.add(label);

      // 點擊命中：直接 raycast 核心 + 輝光 + 標籤（不另建透明球，省 overdraw）
      glow.userData.id = node.id; label.userData.id = node.id; pickables.push(glow, label);
      if (core.isMesh) { core.userData.id = node.id; pickables.push(core); }
      else core.traverse((m) => { if (m.isMesh) { m.userData.id = node.id; pickables.push(m); } });

      scene.add(group);

      // ── 地塊（社區地基）：靜態落在地面，節點漂浮其上，光柱相連 ──
      const plot = new T.Group();
      plot.position.set(node.pos[0], 0, node.pos[2]);
      const pd = new T.Mesh(new T.CylinderGeometry(2.3, 2.55, 0.16, 28),
        new T.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.12, depthWrite: false }));
      plot.add(pd);
      const prg = new T.Mesh(new T.TorusGeometry(2.45, 0.06, 6, 40), addMat(0.5));
      prg.rotation.x = Math.PI / 2; prg.position.y = 0.1; plot.add(prg);
      const pil = new T.Mesh(new T.CylinderGeometry(0.045, 0.045, Math.max(0.4, node.pos[1]), 6),
        new T.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.18, blending: T.AdditiveBlending, depthWrite: false }));
      pil.position.y = node.pos[1] / 2; plot.add(pil);
      scene.add(plot); plots.push({ grp: plot, ring: prg, color: node.color });

      nodeObjs[node.id] = { group, core, wire, ring, glow, label, color: node.color, node, kind, spin, basePos: group.position.clone(), phase: Math.random() * 6.28, pulse: 0, lit: 0 };

      // 若有設定 glTF 模型 → 載入並替換程序化模型（找不到 / 失敗 → 保留程序化版）
      const mc = L.MODELS && L.MODELS[node.id];
      if (mc && T.GLTFLoader) loadModel(mc, group, nodeObjs[node.id], core, wire, ring, statics);
    });
  }

  let _gltfLoader;
  function loadModel(mc, group, obj, core, wire, ring, statics) {
    try {
      _gltfLoader = _gltfLoader || new T.GLTFLoader();
      // 優先用內嵌 base64（file:// 免伺服器）；沒有才讀檔案路徑
      const src = (global.LOBSTER_MODEL_DATA && global.LOBSTER_MODEL_DATA[mc.url]) || mc.url;
      _gltfLoader.load(src, (g) => {
        const m = g.scene;
        const sc = mc.scale == null ? 1 : mc.scale;
        m.scale.setScalar(sc);
        if (mc.rot) m.rotation.set(mc.rot[0] || 0, mc.rot[1] || 0, mc.rot[2] || 0);
        m.position.y = mc.yOff || 0;
        group.add(m);
        if (core) core.visible = false;        // 隱藏程序化模型，保留 glow + label
        if (wire) wire.visible = false;
        if (ring) ring.visible = false;
        statics.forEach((s) => s.visible = false);
        obj.modelRoot = m; obj.modelBaseScale = sc; obj.modelSpin = mc.spin == null ? 0.3 : mc.spin;
        // 模型自帶動畫 → 播放（可用 mc.anim 指定 clip 名，否則播第一個）
        if (g.animations && g.animations.length) {
          const mixer = new T.AnimationMixer(m);
          const clip = (mc.anim && T.AnimationClip.findByName(g.animations, mc.anim)) || g.animations[0];
          mixer.clipAction(clip).play();
          mixers.push(mixer);
        }
      }, undefined, (e) => { console.warn("[glTF] 載入失敗，保留程序化模型:", mc.url, e && e.message); });
    } catch (e) { console.warn("[glTF] loader error", e); }
  }

  function wireOf(geo, col) {
    return new T.LineSegments(new T.WireframeGeometry(geo),
      new T.LineBasicMaterial({ color: col, transparent: true, opacity: 0.4 }));
  }

  /* ── 區域工作流標籤（大字、半透明、面向相機）─────────── */
  function buildRegions() {
    if (!L.REGIONS) return;
    L.REGIONS.forEach((r) => {
      const sp = new T.Sprite(new T.SpriteMaterial({ map: regionTex(r.label, r.color), transparent: true, depthWrite: false, depthTest: false, opacity: 0.62 }));
      sp.scale.set(8, 2, 1);
      sp.position.set(r.pos[0], r.pos[1], r.pos[2]);
      sp.renderOrder = 2;
      scene.add(sp);
    });
  }
  function regionTex(text, color) {
    const W = 600, H = 150, s = 2;
    const cv = document.createElement("canvas"); cv.width = W * s; cv.height = H * s;
    const ctx = cv.getContext("2d"); ctx.scale(s, s);
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = '800 58px "Microsoft JhengHei","Noto Sans TC",sans-serif';
    ctx.fillStyle = color; ctx.shadowColor = color; ctx.shadowBlur = 18;
    ctx.fillText(text, W / 2, H / 2 - 8);
    ctx.shadowBlur = 0;
    const tw = ctx.measureText(text).width;
    ctx.strokeStyle = color; ctx.globalAlpha = 0.6; ctx.lineWidth = 3;
    ctx.beginPath(); ctx.moveTo(W / 2 - tw / 2, H / 2 + 32); ctx.lineTo(W / 2 + tw / 2, H / 2 + 32); ctx.stroke();
    // 兩端小方點
    ctx.globalAlpha = 0.9; ctx.fillStyle = color;
    ctx.fillRect(W / 2 - tw / 2 - 5, H / 2 + 28, 8, 8); ctx.fillRect(W / 2 + tw / 2 - 3, H / 2 + 28, 8, 8);
    const tex = new T.CanvasTexture(cv); tex.anisotropy = 4; return tex;
  }

  /* ── 貼圖工具 ───────────────────────────────────────── */
  function glowTex(color) {
    const k = "g" + color; if (glowTex[k]) return glowTex[k];
    const S = 256, cv = document.createElement("canvas"); cv.width = cv.height = S;
    const ctx = cv.getContext("2d");
    const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    g.addColorStop(0, hexA(color, 0.6)); g.addColorStop(0.4, hexA(color, 0.16)); g.addColorStop(1, hexA(color, 0));
    ctx.fillStyle = g; ctx.fillRect(0, 0, S, S);
    return (glowTex[k] = new T.CanvasTexture(cv));
  }
  function labelTex(node) {
    const W = 440, H = 150, s = 2;
    const cv = document.createElement("canvas"); cv.width = W * s; cv.height = H * s;
    const ctx = cv.getContext("2d"); ctx.scale(s, s);
    roundRect(ctx, 6, 6, W - 12, H - 12, 18);
    ctx.fillStyle = "rgba(6,10,20,0.82)"; ctx.fill();
    ctx.lineWidth = 2; ctx.strokeStyle = hexA(node.color, 0.7); ctx.stroke();
    ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = '40px "Segoe UI Emoji","Noto Color Emoji",sans-serif';
    ctx.fillText(node.icon, 44, H / 2 - 14);
    ctx.fillStyle = "#e8eefc";
    ctx.font = '800 40px "Microsoft JhengHei","Noto Sans TC",sans-serif';
    ctx.fillText(node.label, W / 2 + 18, H / 2 - 16);
    ctx.fillStyle = hexA(node.color, 0.85);
    ctx.font = '500 23px "JetBrains Mono","Microsoft JhengHei",monospace';
    ctx.fillText(node.sub, W / 2, H / 2 + 32);
    const tex = new T.CanvasTexture(cv); tex.anisotropy = 4; return tex;
  }

  /* =======================================================================
   * 光束 + 封包
   * ==================================================================== */
  function nodePos(id) { const n = L.NODES.find((x) => x.id === id); return new T.Vector3(n.pos[0], n.pos[1], n.pos[2]); }
  function curveBetween(from, to) {
    const key = from + ">" + to; if (curves[key]) return curves[key];
    const a = nodePos(from), b = nodePos(to);
    const mid = a.clone().add(b).multiplyScalar(0.5);
    const dist = a.distanceTo(b);
    mid.y += Math.min(6, 2.2 + dist * 0.18); // 資料弧線拱過村落上空（攤平後改用垂直拱起）
    return (curves[key] = new T.QuadraticBezierCurve3(a, mid, b));
  }

  function buildBeams() {
    L.EDGES.forEach((e) => {
      const curve = curveBetween(e.from, e.to);
      const color = colHex(L.EDGE_COLOR[e.kind] || 0x00d9ff);
      const tube = new T.Mesh(new T.TubeGeometry(curve, 44, e.dashed ? 0.02 : 0.035, 8, false),
        new T.MeshBasicMaterial({ color, transparent: true, opacity: e.dashed ? 0.14 : 0.24, blending: T.AdditiveBlending, depthWrite: false }));
      scene.add(tube);
      beams.push({ curve, tube, from: e.from, to: e.to, color, base: e.dashed ? 0.14 : 0.24, glowT: 0 });
    });
  }

  function packetTex() {
    if (packetTex._t) return packetTex._t;
    const S = 64, cv = document.createElement("canvas"); cv.width = cv.height = S;
    const ctx = cv.getContext("2d");
    const g = ctx.createRadialGradient(S / 2, S / 2, 0, S / 2, S / 2, S / 2);
    g.addColorStop(0, "rgba(255,255,255,1)"); g.addColorStop(0.35, "rgba(255,255,255,0.7)"); g.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = g; ctx.fillRect(0, 0, S, S);
    return (packetTex._t = new T.CanvasTexture(cv));
  }
  function msgTex(text, color) {
    const W = 300, H = 56, s = 2;
    const cv = document.createElement("canvas"); cv.width = W * s; cv.height = H * s;
    const ctx = cv.getContext("2d"); ctx.scale(s, s);
    roundRect(ctx, 3, 3, W - 6, H - 6, 14); ctx.fillStyle = "rgba(4,8,16,0.9)"; ctx.fill();
    ctx.lineWidth = 1.5; ctx.strokeStyle = hexA(color, 0.85); ctx.stroke();
    ctx.fillStyle = "#eaf2ff"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
    ctx.font = '700 24px "Microsoft JhengHei","JetBrains Mono",sans-serif';
    let t = String(text); if (t.length > 16) t = t.slice(0, 15) + "…";
    ctx.fillText(t, W / 2, H / 2);
    return new T.CanvasTexture(cv);
  }

  /** 沿 from→to 發射一顆封包；opts: { color, label, big, speed } */
  function sendPacket(from, to, opts) {
    if (paused || !nodeObjs[from] || !nodeObjs[to]) return; // 場景暫停時不堆積封包
    opts = opts || {};
    const curve = curveBetween(from, to);
    const color = colHex(opts.color || nodeObjs[from].color);
    const grp = new T.Group();
    const size = opts.big ? 0.5 : 0.32;
    const oct = new T.Mesh(new T.OctahedronGeometry(size, 0),
      new T.MeshBasicMaterial({ color }));
    grp.add(oct);
    const halo = new T.Sprite(new T.SpriteMaterial({ map: packetTex(), color, transparent: true, blending: T.AdditiveBlending, depthWrite: false }));
    halo.scale.setScalar(opts.big ? 2.4 : 1.6); grp.add(halo);
    let msg = null;
    if (opts.label) {
      msg = new T.Sprite(new T.SpriteMaterial({ map: msgTex(opts.label, opts.color || nodeObjs[from].color), transparent: true, depthWrite: false, depthTest: false }));
      msg.scale.set(3.4, 0.64, 1); msg.position.y = 0.9; msg.renderOrder = 11; grp.add(msg);
    }
    scene.add(grp);
    // 光束高亮
    const beam = beams.find((b) => b.from === from && b.to === to);
    if (beam) beam.glowT = 1;
    packets.push({ grp, oct, msg, curve, t: 0, speed: opts.speed || 0.7, to, color, big: opts.big });
  }

  /* =======================================================================
   * 每幀
   * ==================================================================== */
  let _frames = 0, _slow = 0;
  function animate() {
    if (paused) return;
    requestAnimationFrame(animate);
    const rawDt = clock.getDelta();
    const dt = frozen ? 0 : Math.min(rawDt, 0.05); // 凍結 → 所有時間動畫停住（封包停在半空）
    const t = frozen ? _frozenT : clock.elapsedTime;
    for (let i = 0; i < mixers.length; i++) mixers[i].update(dt); // glTF 動畫

    // 效能保護：bloom 在弱 GPU/軟體渲染會卡，前幾幀偵測到過慢就立刻關閉退回一般渲染
    if (useBloom && _frames < 12) {
      _frames++;
      if (rawDt > 0.07) _slow++;
      if (_frames === 12 && _slow >= 6) { useBloom = false; }
    }

    // 相機
    if (!cam.focusing) {
      cam.theta += cam.velTheta; cam.phi += cam.velPhi;
      cam.velTheta *= 0.92; cam.velPhi *= 0.92; cam.idleTimer += dt;
      if (cam.autoRotate && cam.idleTimer > 3 && !dragging) cam.theta += dt * 0.05;
      cam.phi = Math.max(0.25, Math.min(Math.PI - 0.25, cam.phi));
      updateCamera();
    } else {
      cam.target.lerp(cam.focusTarget, 0.1);
      cam.radius += (cam.focusRadius - cam.radius) * 0.1;
      cam.theta += (cam.toTheta - cam.theta) * 0.1; cam.phi += (cam.toPhi - cam.phi) * 0.1;
      cam.velTheta = cam.velPhi = 0; updateCamera();
      if (cam.target.distanceTo(cam.focusTarget) < 0.05 && Math.abs(cam.radius - cam.focusRadius) < 0.1 && Math.abs(cam.theta - cam.toTheta) < 0.01) cam.focusing = false;
    }

    // 節點動畫
    for (const id in nodeObjs) {
      const o = nodeObjs[id];
      o.group.position.y = o.basePos.y + Math.sin(t * 0.7 + o.phase) * 0.13;
      if (o.spin.y) o.core.rotation.y += dt * o.spin.y;
      if (o.kind === "orb") o.core.rotation.x += dt * 0.2;
      if (o.ring && o.spin.ring) { o.ring.rotation.y += dt * o.spin.ring; o.ring.rotation.z += dt * 0.15; }
      if (o.wire) o.wire.rotation.copy(o.core.rotation);
      const breathe = 0.85 + Math.sin(t * 1.4 + o.phase) * 0.12;
      const ps = 1 + o.pulse * 0.4;
      o.core.scale.setScalar((id === hovered ? 1.12 : 1) * ps);
      if (o.wire) o.wire.scale.setScalar((id === hovered ? 1.12 : 1) * ps);
      if (o.modelRoot) { // 載入的 glTF 模型：自轉 + 受擊放大
        if (o.modelSpin) o.modelRoot.rotation.y += dt * o.modelSpin;
        o.modelRoot.scale.setScalar(o.modelBaseScale * (id === hovered ? 1.12 : 1) * ps);
      }
      o.glow.material.opacity = 0.4 + 0.22 * breathe + o.pulse * 0.7 + o.lit * 0.5;
      o.glow.scale.setScalar(6.2 + breathe + o.pulse * 4 + o.lit * 2);
      if (o.wire) o.wire.material.opacity = (themeLight ? 0.85 : 0.4) + Math.min(0.55, o.pulse * 0.6); // 受擊時線框變亮
      if (!frozen) { o.pulse *= 0.94; o.lit *= 0.95; }
    }

    // 光束高亮衰退（淺色主題加深以利白底辨識）
    for (const b of beams) { b.tube.material.opacity = (themeLight ? 0.5 : b.base) + b.glowT * 0.6; if (!frozen) b.glowT *= 0.95; }

    // 封包飛行
    for (let i = packets.length - 1; i >= 0; i--) {
      const p = packets[i];
      p.t += p.speed * dt;
      if (p.oct) p.oct.rotation.x += dt * 3, p.oct.rotation.y += dt * 4;
      if (p.t >= 1) {
        if (nodeObjs[p.to]) nodeObjs[p.to].pulse = Math.max(nodeObjs[p.to].pulse, p.big ? 1.3 : 0.8);
        scene.remove(p.grp); disposeGroup(p.grp); packets.splice(i, 1); continue;
      }
      p.curve.getPoint(p.t, p.grp.position);
      if (p.msg) p.msg.material.opacity = p.t < 0.12 ? p.t / 0.12 : (p.t > 0.8 ? (1 - p.t) / 0.2 : 1);
    }

    if (starField) starField.rotation.y += dt * 0.004;
    // bloom 渲染若在某些 GPU 出錯，安全退回一般渲染（不讓場景整個壞掉）
    if (useBloom) { try { composer.render(); } catch (e) { useBloom = false; renderer.render(scene, camera); } }
    else renderer.render(scene, camera);
  }

  function updateCamera() {
    const { radius: r, theta: th, phi: ph, target } = cam;
    camera.position.set(target.x + r * Math.sin(ph) * Math.sin(th), target.y + r * Math.cos(ph), target.z + r * Math.sin(ph) * Math.cos(th));
    camera.lookAt(target);
  }

  /* =======================================================================
   * 事件
   * ==================================================================== */
  function bindEvents() {
    const c = renderer.domElement;
    c.style.cursor = "grab";
    c.addEventListener("pointerdown", (e) => {
      dragging = true;
      // 右鍵拖曳 或 Shift+左鍵拖曳 = 平移整個畫面；一般左鍵 = 旋轉
      panning = (e.button === 2) || e.shiftKey === true;
      cam.focusing = false; moved = 0; downX = lastX = e.clientX; downY = lastY = e.clientY; cam.idleTimer = 0;
      c.style.cursor = panning ? "move" : "grabbing";
    });
    window.addEventListener("pointermove", (e) => {
      if (paused) return;
      if (dragging) {
        const dx = e.clientX - lastX, dy = e.clientY - lastY; lastX = e.clientX; lastY = e.clientY;
        moved += Math.abs(dx) + Math.abs(dy); cam.idleTimer = 0;
        if (panning) { panCamera(dx, dy); cam.velTheta = cam.velPhi = 0; }
        else { cam.velTheta = -dx * 0.005; cam.velPhi = -dy * 0.005; }
      } else { updatePointer(e); doHover(e); }
    });
    window.addEventListener("pointerup", (e) => {
      if (dragging && !panning && moved < 6) handleClick(e);
      dragging = false; panning = false; c.style.cursor = "grab";
    });
    c.addEventListener("contextmenu", (e) => e.preventDefault()); // 右鍵拖曳平移：擋掉右鍵選單
    c.addEventListener("wheel", (e) => { e.preventDefault(); cam.focusing = false; cam.radius = Math.max(10, Math.min(72, cam.radius * (1 + Math.sign(e.deltaY) * 0.08))); cam.idleTimer = 0; }, { passive: false });
    window.addEventListener("resize", onResize);
  }
  // 平移：沿相機的右/上向量移動目標點 → 整個 3D 畫面跟著拖
  function panCamera(dx, dy) {
    const fov = camera.fov * Math.PI / 180;
    const k = (2 * cam.radius * Math.tan(fov / 2)) / window.innerHeight;
    const right = new T.Vector3().setFromMatrixColumn(camera.matrixWorld, 0);
    const up = new T.Vector3().setFromMatrixColumn(camera.matrixWorld, 1);
    cam.target.addScaledVector(right, -dx * k);
    cam.target.addScaledVector(up, dy * k);
  }
  function updatePointer(e) { pointer.x = (e.clientX / window.innerWidth) * 2 - 1; pointer.y = -(e.clientY / window.innerHeight) * 2 + 1; }
  function pickNode() {
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects(pickables, false);
    return hits.length ? hits[0].object.userData.id : null;
  }
  function doHover(e) {
    const id = pickNode();
    if (id !== hovered) { hovered = id; renderer.domElement.style.cursor = id ? "pointer" : "grab"; cbHover.forEach((fn) => fn(id, e)); }
    else if (id) cbHover.forEach((fn) => fn(id, e));
  }
  function handleClick(e) { updatePointer(e); const id = pickNode(); if (id) { focusNode(id, { panel: true }); cbClick.forEach((fn) => fn(id)); } }
  function onResize() {
    camera.aspect = window.innerWidth / window.innerHeight; camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
    if (useBloom) { composer.setSize(window.innerWidth, window.innerHeight); bloomPass.resolution.set(window.innerWidth, window.innerHeight); }
    if (cam.mode === "free") { const r = fitRadius(); cam.radius = r; cam.focusRadius = r; }
  }

  /* =======================================================================
   * 對外 API
   * ==================================================================== */
  function focusNode(id, opts) {
    const o = nodeObjs[id]; if (!o) return; opts = opts || {};
    cam.autoRotate = false; cam.focusing = true; cam.mode = "node";
    const tgt = o.basePos.clone();
    if (opts.panel) { const dir = new T.Vector3(); camera.getWorldDirection(dir); const right = dir.clone().cross(camera.up).normalize(); tgt.add(right.multiplyScalar(5.5)); }
    cam.focusTarget = tgt; cam.focusRadius = opts.panel ? 15 : 11; cam.toTheta = cam.theta; cam.toPhi = cam.phi; o.pulse = 1.2;
  }
  function overview() { cam.autoRotate = false; cam.focusing = true; cam.mode = "free"; cam.focusTarget = new T.Vector3(0, 0.6, 1); cam.focusRadius = fitRadius(0.9); cam.toTheta = -0.4; cam.toPhi = 0.86; cam.idleTimer = 0; }
  function reset() { cam.autoRotate = true; cam.focusing = true; cam.mode = "free"; cam.focusTarget = new T.Vector3(0, 0.8, 1); cam.focusRadius = fitRadius(); cam.toTheta = -0.42; cam.toPhi = 0.92; cam.idleTimer = 0; }
  function litNode(id, amt) { if (nodeObjs[id]) nodeObjs[id].pulse = Math.max(nodeObjs[id].pulse, amt == null ? 1.2 : amt); }
  // 相容舊 API：boostEdge → 發一顆封包
  function boostEdge(from, to, opts) { sendPacket(from, to, typeof opts === "object" ? opts : {}); }
  function getScreenPos(id) {
    const o = nodeObjs[id]; if (!o) return null;
    const v = o.group.position.clone().project(camera);
    return { x: (v.x * 0.5 + 0.5) * window.innerWidth, y: (-v.y * 0.5 + 0.5) * window.innerHeight, visible: v.z < 1 };
  }
  function setActive(on) { if (on) { if (paused) { paused = false; clock.getDelta(); animate(); } } else paused = true; }
  // 凍結：停住時間動畫（封包停在半空），但保持渲染 + 相機可旋轉/縮放查看
  function setFrozen(on) { if (on && !frozen) _frozenT = clock ? clock.elapsedTime : 0; frozen = on; }

  // 深色 / 淺色主題：換背景 + 關 bloom + 調整線框/光束/輝光在白底的可見度
  function setTheme(light) {
    themeLight = light;
    if (!scene) return;
    const bg = light ? 0xeef1f7 : 0x04060f;
    scene.background.set(bg);
    if (scene.fog) scene.fog.color.set(bg);
    if (light) useBloom = false; // 白底上 bloom 無意義
    if (starField) starField.material.color.set(light ? 0x9fb0cc : 0x3a4a6b);
    for (const id in nodeObjs) {
      const o = nodeObjs[id];
      if (o.glow) o.glow.visible = !light;   // 輝光在白底看不到 → 關掉
    }
    for (const b of beams) {
      b.tube.material.blending = light ? T.NormalBlending : T.AdditiveBlending;
      b.tube.material.needsUpdate = true;
    }
  }

  /* ── 工具 ───────────────────────────────────────────── */
  function roundRect(ctx, x, y, w, h, r) { ctx.beginPath(); ctx.moveTo(x + r, y); ctx.arcTo(x + w, y, x + w, y + h, r); ctx.arcTo(x + w, y + h, x, y + h, r); ctx.arcTo(x, y + h, x, y, r); ctx.arcTo(x, y, x + w, y, r); ctx.closePath(); }
  function hexA(hex, a) { const h = hex.replace("#", ""); const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16); return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`; }
  function disposeGroup(g) { g.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) { if (o.material.map) o.material.map.dispose && o.material.map.dispose(); o.material.dispose(); } }); }

  global.LOBSTER_SCENE = {
    init, setActive, setFrozen, setTheme, focusNode, overview, reset, litNode, boostEdge, sendPacket, getScreenPos,
    getNode: (id) => nodeObjs[id],
    onHover: (fn) => cbHover.push(fn), onClick: (fn) => cbClick.push(fn),
  };
})(window);
