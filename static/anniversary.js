(() => {
    // A brief welcome celebration; respect the visitor's motion preference.
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    if (reducedMotion.matches) return;

    const canvas = document.createElement('canvas');
    canvas.setAttribute('aria-hidden', 'true');
    Object.assign(canvas.style, {
        position: 'fixed', inset: '0', width: '100%', height: '100%',
        pointerEvents: 'none', zIndex: '100',
    });
    const context = canvas.getContext('2d');
    if (!context) return;
    document.body.appendChild(canvas);

    let width, height, frame, started, previous;
    let particles = [];
    let burstIndex = 0;
    let stopped = false;
    const colors = ['#f8df9c', '#d3a657', '#fff2c8', '#5889cf', '#9dbce9'];
    const bursts = [
        { time: 120, x: 0.18, y: 0.23 },
        { time: 440, x: 0.82, y: 0.19 },
        { time: 820, x: 0.5, y: 0.12 },
    ];

    function resize() {
        width = window.innerWidth;
        height = window.innerHeight;
        const ratio = Math.min(window.devicePixelRatio || 1, 2);
        canvas.width = Math.round(width * ratio);
        canvas.height = Math.round(height * ratio);
        context.setTransform(ratio, 0, 0, ratio, 0, 0);
    }

    function burst(position) {
        const count = width < 600 ? 32 : 48;
        for (let i = 0; i < count; i++) {
            const angle = Math.random() * Math.PI * 2;
            const speed = 85 + Math.random() * 165;
            particles.push({
                x: width * position.x, y: Math.min(height, 800) * position.y,
                vx: Math.cos(angle) * speed, vy: Math.sin(angle) * speed - 70,
                rotation: Math.random() * Math.PI, spin: (Math.random() - 0.5) * 8,
                age: 0, life: 1.5 + Math.random() * 0.7,
                size: 3 + Math.random() * 4,
                color: colors[Math.floor(Math.random() * colors.length)],
            });
        }
    }

    function stop() {
        if (stopped) return;
        stopped = true;
        cancelAnimationFrame(frame);
        canvas.remove();
        window.removeEventListener('resize', resize);
        window.removeEventListener('pagehide', stop);
        document.removeEventListener('visibilitychange', visibilityChanged);
        reducedMotion.removeEventListener('change', motionChanged);
    }

    function visibilityChanged() {
        if (document.hidden) stop();
    }

    function motionChanged() {
        if (reducedMotion.matches) stop();
    }

    function animate(now) {
        if (stopped) return;
        if (started === undefined) started = previous = now;
        const elapsed = now - started;
        const delta = Math.min((now - previous) / 1000, 0.04);
        previous = now;
        if (elapsed > 3400) { stop(); return; }
        while (burstIndex < bursts.length && elapsed >= bursts[burstIndex].time) {
            burst(bursts[burstIndex++]);
        }
        context.clearRect(0, 0, width, height);
        particles = particles.filter(p => p.age < p.life);
        for (const p of particles) {
            p.age += delta;
            p.vy += 170 * delta;
            p.vx *= Math.exp(-1.2 * delta);
            p.x += p.vx * delta;
            p.y += p.vy * delta;
            p.rotation += p.spin * delta;
            context.save();
            context.globalAlpha = Math.max(0, Math.min(1, (p.life - p.age) / 0.7));
            context.translate(p.x, p.y);
            context.rotate(p.rotation);
            context.fillStyle = p.color;
            context.fillRect(-p.size / 2, -p.size, p.size, p.size * 2);
            context.restore();
        }
        frame = requestAnimationFrame(animate);
    }

    resize();
    window.addEventListener('resize', resize);
    window.addEventListener('pagehide', stop);
    document.addEventListener('visibilitychange', visibilityChanged);
    reducedMotion.addEventListener('change', motionChanged);
    frame = requestAnimationFrame(animate);
})();
