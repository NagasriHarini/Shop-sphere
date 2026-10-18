/* ShopSphere UI helpers: 3D tilt, theme, menus, flash, reveal, password tools */
(function () {
  const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fine = window.matchMedia('(pointer: fine)').matches;

  /* ---- Theme (light / dark), remembered per browser ---- */
  const root = document.documentElement;
  const themeBtn = document.getElementById('themeToggle');
  if (themeBtn) {
    themeBtn.addEventListener('click', () => {
      const dark = root.dataset.theme
        ? root.dataset.theme === 'dark'
        : window.matchMedia('(prefers-color-scheme: dark)').matches;
      root.dataset.theme = dark ? 'light' : 'dark';
      try { localStorage.setItem('theme', root.dataset.theme); } catch (e) {}
    });
  }

  /* ---- Mobile menu + dropdowns ---- */
  const header = document.querySelector('.site-header');
  const menuBtn = document.getElementById('menuToggle');
  if (menuBtn && header) menuBtn.addEventListener('click', () => header.classList.toggle('open'));
  document.querySelectorAll('[data-dropdown]').forEach(dd => {
    const btn = dd.querySelector('.nav-btn');
    btn.addEventListener('click', e => { e.stopPropagation(); dd.classList.toggle('open'); });
  });
  document.addEventListener('click', () => document.querySelectorAll('[data-dropdown].open').forEach(d => d.classList.remove('open')));

  /* ---- Flash messages fade away ---- */
  document.querySelectorAll('.flash-stack .alert').forEach((el, i) => {
    setTimeout(() => { el.style.transition = 'opacity .4s, transform .4s'; el.style.opacity = '0'; el.style.transform = 'translateX(30px)'; }, 4200 + i * 400);
    setTimeout(() => el.remove(), 4700 + i * 400);
  });

  /* ---- 3D tilt: any element with [data-tilt] ---- */
  if (!reduce && fine) {
    document.querySelectorAll('[data-tilt]').forEach(el => {
      const max = parseFloat(el.dataset.tilt) || 10;
      let raf = null;
      el.addEventListener('pointermove', e => {
        const r = el.getBoundingClientRect();
        const x = (e.clientX - r.left) / r.width, y = (e.clientY - r.top) / r.height;
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
          el.style.setProperty('--ry', ((x - 0.5) * 2 * max).toFixed(2) + 'deg');
          el.style.setProperty('--rx', ((0.5 - y) * 2 * max).toFixed(2) + 'deg');
          el.style.setProperty('--gx', (x * 100).toFixed(1) + '%');
          el.style.setProperty('--gy', (y * 100).toFixed(1) + '%');
        });
      });
      el.addEventListener('pointerleave', () => {
        cancelAnimationFrame(raf);
        el.style.setProperty('--rx', '0deg'); el.style.setProperty('--ry', '0deg');
      });
    });
  }

  /* ---- Hero parallax for floating orbs ---- */
  const stage = document.querySelector('.stage');
  if (stage && !reduce && fine) {
    const orbs = stage.querySelectorAll('.orb');
    stage.addEventListener('pointermove', e => {
      const r = stage.getBoundingClientRect();
      const x = (e.clientX - r.left) / r.width - 0.5, y = (e.clientY - r.top) / r.height - 0.5;
      orbs.forEach((o, i) => { const d = (i + 1) * 14; o.style.translate = `${x * d}px ${y * d}px`; });
    });
  }

  /* ---- Reveal on scroll ---- */
  const reveals = document.querySelectorAll('.reveal');
  if (reveals.length) {
    if (reduce || !('IntersectionObserver' in window)) reveals.forEach(r => r.classList.add('in'));
    else {
      const io = new IntersectionObserver(entries => entries.forEach(en => {
        if (en.isIntersecting) { en.target.classList.add('in'); io.unobserve(en.target); }
      }), { threshold: 0.12 });
      reveals.forEach((r, i) => { r.style.transitionDelay = (i % 6) * 60 + 'ms'; io.observe(r); });
    }
  }

  /* ---- Password show / hide ---- */
  document.querySelectorAll('[data-toggle-password]').forEach(btn => {
    btn.addEventListener('click', () => {
      const input = document.getElementById(btn.dataset.togglePassword);
      const show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.textContent = show ? 'Hide' : 'Show';
    });
  });

  /* ---- Password strength meter ---- */
  const pw = document.querySelector('[data-strength]');
  if (pw) {
    const bar = document.querySelector(pw.dataset.strength + ' i');
    const txt = document.querySelector(pw.dataset.strength + '-text');
    pw.addEventListener('input', () => {
      const v = pw.value; let s = 0;
      if (v.length >= 8) s++; if (/[A-Z]/.test(v)) s++; if (/[0-9]/.test(v)) s++; if (/[^A-Za-z0-9]/.test(v)) s++;
      const steps = [['0%', '#e02424', ''], ['25%', '#e02424', 'Weak'], ['50%', '#c27803', 'Fair'], ['75%', '#0e9f6e', 'Good'], ['100%', '#0e9f6e', 'Strong']];
      const [w, c, t] = v ? steps[s] : steps[0];
      bar.style.width = w; bar.style.background = c; if (txt) txt.textContent = t;
    });
  }

  /* ---- Confirm before destructive submits ---- */
  document.querySelectorAll('form[data-confirm]').forEach(f => f.addEventListener('submit', e => {
    if (!window.confirm(f.dataset.confirm)) e.preventDefault();
  }));
})();
