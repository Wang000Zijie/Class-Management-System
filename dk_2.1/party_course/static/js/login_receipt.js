import * as THREE from "../vendor/three.module.js";

(function initLoginPaper() {
  const mount = document.getElementById("receipt-scene");
  const fallbackCard = document.getElementById("receipt-fallback");
  const tip = document.querySelector(".scene-tip");

  if (!mount) {
    return;
  }

  const receiptData = {
    semesterName: mount.dataset.semesterName || "未设置激活学期",
    periodPositive: mount.dataset.periodPositive || "未设置",
    periodDevelopment: mount.dataset.periodDevelopment || "未设置",
    periodProbationary: mount.dataset.periodProbationary || "未设置",
  };

  function showFallback(msg) {
    if (fallbackCard) {
      fallbackCard.classList.remove("hidden");
    }
    if (tip && msg) {
      tip.textContent = msg;
    }
  }

  function hideFallback() {
    if (fallbackCard) {
      fallbackCard.classList.add("hidden");
    }
  }

  function wrapText(ctx, text, x, y, maxWidth, lineHeight) {
    const chars = String(text || "").split("");
    let line = "";
    for (let i = 0; i < chars.length; i += 1) {
      const test = line + chars[i];
      if (ctx.measureText(test).width > maxWidth && line) {
        ctx.fillText(line, x, y);
        line = chars[i];
        y += lineHeight;
      } else {
        line = test;
      }
    }
    if (line) {
      ctx.fillText(line, x, y);
      y += lineHeight;
    }
    return y;
  }

  function drawSectionTitle(ctx, text, y, left, right) {
    ctx.fillStyle = "#2f2f2f";
    ctx.font = '700 30px "Consolas", "Courier New", monospace';
    ctx.fillText(text, left, y);
    ctx.strokeStyle = "rgba(55, 55, 55, 0.28)";
    ctx.beginPath();
    ctx.moveTo(left, y + 14);
    ctx.lineTo(right, y + 14);
    ctx.stroke();
    return y + 52;
  }

  function createReceiptTexture(renderer) {
    const canvas = document.createElement("canvas");
    canvas.width = 2048;
    canvas.height = 1820;
    const ctx = canvas.getContext("2d");

    const bg = ctx.createLinearGradient(0, 0, 0, canvas.height);
    bg.addColorStop(0, "#fffef9");
    bg.addColorStop(1, "#f8f4e9");
    ctx.fillStyle = bg;
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    for (let i = 0; i < 14000; i += 1) {
      const x = Math.random() * canvas.width;
      const y = Math.random() * canvas.height;
      const alpha = 0.02 + Math.random() * 0.03;
      const v = 188 + Math.floor(Math.random() * 48);
      ctx.fillStyle = `rgba(${v}, ${v}, ${v - 6}, ${alpha})`;
      ctx.fillRect(x, y, 1, 1);
    }

    const left = 120;
    const right = canvas.width - 120;
    const maxW = right - left;

    ctx.fillStyle = "#2f2f2f";
    ctx.font = '700 88px "Consolas", "Courier New", monospace';
    ctx.fillText("PARTY COURSE PAPER", left, 130);
    ctx.font = '500 44px "Microsoft YaHei", sans-serif';
    ctx.fillText("党课管理系统 · 登录页动态纸张引导", left, 190);
    ctx.fillRect(left, 220, maxW, 5);

    let y = 300;
    y = drawSectionTitle(ctx, "SYSTEM ACCOUNTS", y, left, right);
    ctx.fillStyle = "#353535";
    ctx.font = '600 40px "Consolas", "Courier New", monospace';
    ctx.fillText("主席账号 : admin", left, y);
    ctx.fillText("部长账号 : buzhang", left + 620, y);
    y += 56;
    ctx.fillText("干事账号 : ganshi", left, y);
    y += 52;
    ctx.font = '500 34px "Microsoft YaHei", sans-serif';
    y = wrapText(ctx, "密码以系统当前配置为准，若已重置请使用管理员通知的新密码。", left, y, maxW, 46);

    y += 12;
    y = drawSectionTitle(ctx, "CURRENT SEMESTER", y, left, right);
    ctx.font = '600 34px "Microsoft YaHei", sans-serif';
    ctx.fillText(`学期：${receiptData.semesterName}`, left, y);
    y += 48;
    ctx.fillText(`积极分子期数：${receiptData.periodPositive}`, left, y);
    ctx.fillText(`发展对象期数：${receiptData.periodDevelopment}`, left + 620, y);
    y += 48;
    ctx.fillText(`预备党员期数：${receiptData.periodProbationary}`, left, y);

    y += 48;
    y = drawSectionTitle(ctx, "OPERATION GUIDE", y, left, right);
    ctx.font = '500 33px "Microsoft YaHei", sans-serif';
    const guides = [
      "1. 先在学期管理确认并激活本学期",
      "2. 再录入学员、作业、考试、志愿时长数据",
      "3. 进入成绩总览，执行重新计算并校验结果",
      "4. 通过后发放证书，最后导出归档表格",
    ];
    for (const line of guides) {
      y = wrapText(ctx, line, left, y, maxW, 44);
    }

    y += 10;
    y = drawSectionTitle(ctx, "TRAINING RULES", y, left, right);
    ctx.font = '500 31px "Microsoft YaHei", sans-serif';
    const rules = [
      "1. 积极分子心得不少于 1500 字，预备党员不少于 2000 字",
      "2. 志愿时长达标后方可结业，且需完成讨论和实践记录",
      "3. 缺席达总次数三分之一及以上者取消考试资格",
    ];
    for (const line of rules) {
      y = wrapText(ctx, line, left, y, maxW, 42);
    }

    y += 18;
    ctx.strokeStyle = "rgba(48,48,48,0.28)";
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();

    y += 52;
    ctx.font = '700 44px "Consolas", "Courier New", monospace';
    ctx.fillStyle = "#333";
    ctx.fillText("STATUS : READY TO LOGIN", left, y);

    const qrX = canvas.width - 360;
    const qrY = y + 30;
    const s = 24;
    const blocks = [
      [0, 0], [1, 0], [2, 0], [4, 0], [6, 0],
      [0, 1], [2, 1], [3, 1], [6, 1],
      [0, 2], [1, 2], [2, 2], [5, 2], [6, 2],
      [0, 4], [2, 4], [3, 4], [4, 4], [6, 4],
      [0, 5], [4, 5], [6, 5],
      [0, 6], [1, 6], [2, 6], [4, 6], [6, 6],
    ];
    for (const [bx, by] of blocks) {
      ctx.fillRect(qrX + bx * s, qrY + by * s, s - 3, s - 3);
    }

    const tex = new THREE.CanvasTexture(canvas);
    if ("colorSpace" in tex) {
      tex.colorSpace = THREE.SRGBColorSpace;
    }
    tex.anisotropy = Math.min(8, renderer.capabilities.getMaxAnisotropy());
    return tex;
  }

  function createFiberMap() {
    const canvas = document.createElement("canvas");
    canvas.width = 256;
    canvas.height = 256;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "rgb(188, 188, 188)";
    ctx.fillRect(0, 0, 256, 256);

    for (let i = 0; i < 850; i += 1) {
      const x = Math.random() * 256;
      const y = Math.random() * 256;
      const alpha = 0.03 + Math.random() * 0.08;
      const h = 6 + Math.random() * 14;
      ctx.fillStyle = `rgba(255,255,255,${alpha})`;
      ctx.fillRect(x, y, 1, h);
    }

    const tex = new THREE.CanvasTexture(canvas);
    tex.wrapS = THREE.RepeatWrapping;
    tex.wrapT = THREE.RepeatWrapping;
    tex.repeat.set(4, 14);
    return tex;
  }

  try {
    const renderer = new THREE.WebGLRenderer({
      antialias: true,
      alpha: false,
      powerPreference: "high-performance",
    });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.8));
    renderer.setClearColor(0xffffff, 1);
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    if ("outputColorSpace" in renderer) {
      renderer.outputColorSpace = THREE.SRGBColorSpace;
    }
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(34, 1, 0.1, 60);
    camera.position.set(0, 0.25, 5.8);
    camera.lookAt(0, 0.2, 0);

    const hemiLight = new THREE.HemisphereLight(0xffffff, 0xf2f3f7, 1.0);
    scene.add(hemiLight);

    const keyLight = new THREE.DirectionalLight(0xffffff, 1.16);
    keyLight.position.set(2.2, 4.4, 4.2);
    keyLight.castShadow = true;
    keyLight.shadow.mapSize.set(1024, 1024);
    keyLight.shadow.camera.near = 0.2;
    keyLight.shadow.camera.far = 20;
    keyLight.shadow.camera.left = -6;
    keyLight.shadow.camera.right = 6;
    keyLight.shadow.camera.top = 6;
    keyLight.shadow.camera.bottom = -6;
    scene.add(keyLight);

    const fillLight = new THREE.DirectionalLight(0xf8f8ff, 0.45);
    fillLight.position.set(-2.6, 1.8, 3.5);
    scene.add(fillLight);

    const rimLight = new THREE.DirectionalLight(0xffffff, 0.22);
    rimLight.position.set(0.5, 1.8, -3.5);
    scene.add(rimLight);

    const floor = new THREE.Mesh(
      new THREE.PlaneGeometry(16, 16),
      new THREE.ShadowMaterial({ opacity: 0.14 })
    );
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = -3.45;
    floor.receiveShadow = true;
    scene.add(floor);

    const cloth = {
      width: 5.9,
      height: 5.25,
      segX: 34,
      segY: 30,
    };

    const cols = cloth.segX + 1;
    const rows = cloth.segY + 1;
    const particleCount = cols * rows;

    function indexOf(x, y) {
      return y * cols + x;
    }

    const particles = new Array(particleCount);
    const constraints = [];
    const topIndices = [];

    for (let y = 0; y < rows; y += 1) {
      for (let x = 0; x < cols; x += 1) {
        const px = (x / cloth.segX - 0.5) * cloth.width;
        const py = (0.5 - y / cloth.segY) * cloth.height;
        const pinned = y === 0;
        const curve = Math.sin((x / cloth.segX) * Math.PI) * 0.016;
        const pz = pinned ? 0 : curve + (Math.random() - 0.5) * 0.012 * (y / cloth.segY);

        particles[indexOf(x, y)] = {
          x: px,
          y: py,
          z: pz,
          px,
          py,
          pz,
          ax: 0,
          ay: 0,
          az: 0,
          invMass: pinned ? 0 : 1,
          pinX: px,
          pinY: py,
          pinZ: 0,
        };

        if (pinned) {
          topIndices.push(indexOf(x, y));
        }
      }
    }

    function addConstraint(i1, i2, stiffness) {
      const p1 = particles[i1];
      const p2 = particles[i2];
      const dx = p2.x - p1.x;
      const dy = p2.y - p1.y;
      const dz = p2.z - p1.z;
      constraints.push({
        i1,
        i2,
        rest: Math.sqrt(dx * dx + dy * dy + dz * dz),
        stiffness,
      });
    }

    for (let y = 0; y < rows; y += 1) {
      for (let x = 0; x < cols; x += 1) {
        const id = indexOf(x, y);
        if (x < cloth.segX) {
          addConstraint(id, indexOf(x + 1, y), y === 0 ? 1.0 : 0.94);
        }
        if (y < cloth.segY) {
          addConstraint(id, indexOf(x, y + 1), 0.92);
        }
        if (x < cloth.segX && y < cloth.segY) {
          addConstraint(id, indexOf(x + 1, y + 1), 0.78);
        }
        if (x > 0 && y < cloth.segY) {
          addConstraint(id, indexOf(x - 1, y + 1), 0.78);
        }
        if (x < cloth.segX - 1) {
          addConstraint(id, indexOf(x + 2, y), 0.26);
        }
        if (y < cloth.segY - 1) {
          addConstraint(id, indexOf(x, y + 2), 0.24);
        }
      }
    }

    const receiptGeometry = new THREE.PlaneGeometry(cloth.width, cloth.height, cloth.segX, cloth.segY);
    const fiberMap = createFiberMap();
    const receiptMaterial = new THREE.MeshStandardMaterial({
      map: createReceiptTexture(renderer),
      color: 0xfffdf6,
      roughnessMap: fiberMap,
      bumpMap: fiberMap,
      bumpScale: 0.018,
      roughness: 0.93,
      metalness: 0.01,
      side: THREE.DoubleSide,
    });

    const receiptMesh = new THREE.Mesh(receiptGeometry, receiptMaterial);
    receiptMesh.castShadow = true;
    receiptMesh.receiveShadow = true;
    receiptMesh.position.set(0, 0.05, 0);
    scene.add(receiptMesh);

    function enforceTopEdge() {
      for (const id of topIndices) {
        const p = particles[id];
        p.x = p.pinX;
        p.y = p.pinY;
        p.z = p.pinZ;
        p.px = p.pinX;
        p.py = p.pinY;
        p.pz = p.pinZ;
      }
    }

    function solveConstraint(c) {
      const p1 = particles[c.i1];
      const p2 = particles[c.i2];
      const w1 = p1.invMass;
      const w2 = p2.invMass;
      const w = w1 + w2;
      if (w === 0) {
        return;
      }

      let dx = p2.x - p1.x;
      let dy = p2.y - p1.y;
      let dz = p2.z - p1.z;
      const lenSq = dx * dx + dy * dy + dz * dz;
      if (lenSq < 1e-12) {
        return;
      }

      const len = Math.sqrt(lenSq);
      const diff = ((len - c.rest) / len) * c.stiffness;
      dx *= diff;
      dy *= diff;
      dz *= diff;

      if (w1 > 0) {
        const ratio = w1 / w;
        p1.x += dx * ratio;
        p1.y += dy * ratio;
        p1.z += dz * ratio;
      }
      if (w2 > 0) {
        const ratio = w2 / w;
        p2.x -= dx * ratio;
        p2.y -= dy * ratio;
        p2.z -= dz * ratio;
      }
    }

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    const dragPlane = new THREE.Plane();
    const dragPoint = new THREE.Vector3();
    const dragLocal = new THREE.Vector3();
    const camDir = new THREE.Vector3();

    const dragState = {
      active: false,
      index: -1,
      target: new THREE.Vector3(),
      pointerId: null,
      depthKick: 0,
      lastClientY: 0,
    };

    function updatePointer(event) {
      const rect = mount.getBoundingClientRect();
      pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
      pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    }

    function onPointerDown(event) {
      if (event.button !== 0) {
        return;
      }
      updatePointer(event);
      raycaster.setFromCamera(pointer, camera);

      const hit = raycaster.intersectObject(receiptMesh, false)[0];
      if (!hit || !hit.uv) {
        return;
      }

      let x = Math.round(hit.uv.x * cloth.segX);
      let y = Math.round((1 - hit.uv.y) * cloth.segY);
      x = Math.max(0, Math.min(cloth.segX, x));
      y = Math.max(1, Math.min(cloth.segY, y));

      dragState.active = true;
      dragState.index = indexOf(x, y);
      dragState.pointerId = event.pointerId;
      dragState.target.copy(hit.point);
      dragState.lastClientY = event.clientY;
      dragState.depthKick = 0;

      camera.getWorldDirection(camDir);
      dragPlane.setFromNormalAndCoplanarPoint(camDir, hit.point);

      if (mount.setPointerCapture) {
        mount.setPointerCapture(event.pointerId);
      }
      mount.classList.add("grabbing");
    }

    function onPointerMove(event) {
      if (!dragState.active) {
        return;
      }

      updatePointer(event);
      raycaster.setFromCamera(pointer, camera);
      if (raycaster.ray.intersectPlane(dragPlane, dragPoint)) {
        dragState.target.copy(dragPoint);
      }

      const dy = event.clientY - dragState.lastClientY;
      dragState.depthKick = THREE.MathUtils.clamp(dy * -0.0022, -0.08, 0.08);
      dragState.lastClientY = event.clientY;
    }

    function releaseDrag() {
      if (!dragState.active) {
        return;
      }
      if (dragState.pointerId !== null && mount.releasePointerCapture) {
        try {
          mount.releasePointerCapture(dragState.pointerId);
        } catch (_error) {
          // ignore
        }
      }
      dragState.active = false;
      dragState.index = -1;
      dragState.pointerId = null;
      dragState.depthKick = 0;
      mount.classList.remove("grabbing");
    }

    renderer.domElement.addEventListener("pointerdown", onPointerDown);
    renderer.domElement.addEventListener("pointermove", onPointerMove);
    renderer.domElement.addEventListener("pointerup", releaseDrag);
    renderer.domElement.addEventListener("pointercancel", releaseDrag);
    renderer.domElement.addEventListener("pointerleave", releaseDrag);

    function applyDragPull() {
      if (!dragState.active || dragState.index < 0) {
        return;
      }

      dragLocal.copy(dragState.target);
      receiptMesh.worldToLocal(dragLocal);

      const p = particles[dragState.index];
      const pull = 0.46;
      p.x += (dragLocal.x - p.x) * pull;
      p.y += (dragLocal.y - p.y) * pull;
      p.z += (dragLocal.z - p.z) * pull + dragState.depthKick;

      const centerX = dragState.index % cols;
      const centerY = Math.floor(dragState.index / cols);
      for (let oy = -1; oy <= 1; oy += 1) {
        for (let ox = -1; ox <= 1; ox += 1) {
          if (ox === 0 && oy === 0) {
            continue;
          }
          const nx = centerX + ox;
          const ny = centerY + oy;
          if (nx < 0 || nx >= cols || ny < 1 || ny >= rows) {
            continue;
          }
          const neighbor = particles[indexOf(nx, ny)];
          if (neighbor.invMass === 0) {
            continue;
          }
          neighbor.z += dragState.depthKick * 0.45;
        }
      }

      dragState.depthKick *= 0.82;
    }

    let simulationTime = 0;
    function simulate(dt) {
      simulationTime += dt;
      const dtSq = dt * dt;
      const gravity = -18.8;
      const windX = Math.sin(simulationTime * 0.82) * 1.06;
      const windY = Math.cos(simulationTime * 0.43) * 0.2;
      const windZ = Math.cos(simulationTime * 1.08 + 0.35) * 0.84;

      for (let i = 0; i < particleCount; i += 1) {
        const p = particles[i];
        if (p.invMass === 0) {
          continue;
        }

        const depth = (cloth.height * 0.5 - p.pinY) / cloth.height;
        const lift = 0.62 + depth * 1.18;
        p.ax += windX * lift;
        p.ay += gravity + windY * lift;
        p.az += windZ * lift;

        const vx = (p.x - p.px) * 0.992;
        const vy = (p.y - p.py) * 0.992;
        const vz = (p.z - p.pz) * 0.992;

        p.px = p.x;
        p.py = p.y;
        p.pz = p.z;

        p.x += vx + p.ax * dtSq;
        p.y += vy + p.ay * dtSq;
        p.z += vz + p.az * dtSq;

        if (p.y < -2.95) {
          p.y = -2.95;
        }

        p.ax = 0;
        p.ay = 0;
        p.az = 0;
      }

      const iterations = dragState.active ? 6 : 5;
      for (let iter = 0; iter < iterations; iter += 1) {
        applyDragPull();
        for (let i = 0; i < constraints.length; i += 1) {
          solveConstraint(constraints[i]);
        }
        enforceTopEdge();
      }
    }

    const posAttr = receiptGeometry.attributes.position;
    const posArray = posAttr.array;
    function syncGeometry() {
      for (let i = 0; i < particleCount; i += 1) {
        const p = particles[i];
        const base = i * 3;
        posArray[base] = p.x;
        posArray[base + 1] = p.y;
        posArray[base + 2] = p.z;
      }
      posAttr.needsUpdate = true;
      receiptGeometry.computeVertexNormals();
    }

    function resize() {
      const width = mount.clientWidth;
      const height = mount.clientHeight;
      if (!width || !height) {
        return;
      }
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();

      const distance = camera.position.z - receiptMesh.position.z;
      const visibleHeight = 2 * Math.tan(THREE.MathUtils.degToRad(camera.fov * 0.5)) * distance;
      const visibleWidth = visibleHeight * camera.aspect;
      const targetWidth = visibleWidth * 0.96;
      const targetHeight = visibleHeight * 0.93;
      const scale = Math.min(targetWidth / cloth.width, targetHeight / cloth.height);
      receiptMesh.scale.set(scale, scale, 1);
    }

    resize();
    if (window.ResizeObserver) {
      const observer = new ResizeObserver(() => resize());
      observer.observe(mount);
      window.addEventListener("beforeunload", () => observer.disconnect(), { once: true });
    }
    window.addEventListener("resize", resize, { passive: true });

    let active = true;
    let lastTime = performance.now();
    document.addEventListener("visibilitychange", () => {
      active = !document.hidden;
      lastTime = performance.now();
    });

    function frame(now) {
      requestAnimationFrame(frame);
      if (!active) {
        return;
      }

      const dt = Math.min(0.033, Math.max(0.008, (now - lastTime) / 1000));
      lastTime = now;

      const substeps = dragState.active ? 2 : 1;
      const step = dt / substeps;
      for (let i = 0; i < substeps; i += 1) {
        simulate(step);
      }

      syncGeometry();
      renderer.render(scene, camera);
    }

    hideFallback();
    requestAnimationFrame(frame);
  } catch (error) {
    showFallback("动态纸张加载失败，已显示兜底内容。请刷新后重试。" + (error && error.message ? " 原因: " + error.message : ""));
  }
})();
