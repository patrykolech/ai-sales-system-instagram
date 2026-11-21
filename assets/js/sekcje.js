/* sekcje.js (v3): ruch sekcji po hero "Moment w lustrze". GSAP 3.15 + ScrollTrigger + SplitText + DrawSVG (lokalne, przypiete).
   Strona jest kompletna bez tego pliku (stan statyczny w CSS). Lenis tworzy wylacznie main.js (tylko desktop z mysza):
   tu nie powstaje druga instancja, a jedynym zegarem jest gsap.ticker z main.js (lenis.raf + ScrollTrigger.update).

   Kontrakt (naglowek assets/css/sekcje.css):
   - klasy na <html> sa wlasne i niezalezne od html.js hero: .sk (skrypt dziala), .sk-ruch (ruch dozwolony),
     .sk-pin (desktop >= 1100 x 600, poza Instagramem: piny i scrub). Bezpiecznik hero zdejmujacy html.js ich nie dotyka;
   - przy bledzie budowy: mm.revert(), zdjecie .sk-ruch/.sk-pin, jeden console.warn; html.js hero zostaje (to nie nasza scena);
   - animujemy transform, opacity i clip-path jednolitej warstwy przejscia; wyjatek: kreska podpisu w O mnie (DrawSVG, raz);
   - html.lite (przegladarka Instagrama, ustawia main.js): bez pinow i scrubow scen, proste wejscia raz; przejscia sekcji
     (kolo, plynnie, kartka) dzialaja, bo to jedna jednolita warstwa albo natywny sticky;
   - prefers-reduced-motion: reduce: zero ruchu, kompozycje w stanie koncowym, petle stoja, cytaty jako lista, bez przejsc.

   Sceny w kolejnosci strony (sekcje znikaja przy braku danych, kazda funkcja sprawdza swoje elementy):
     0 · niezalezne od GSAP: lightbox, staly przycisk i staly spis (sekcja pod punktem ekranu), kotwice, plynne <details>,
         puderniczka w kontakcie (WAAPI)
     1 · tasma pod hero: petla, predkosc i kierunek z predkosci przewijania
     2 · galeria luster: lusterka z roznych glebokosci skladaja sie wokol naglowka (desktop pin + scrub, telefon scrub)
     3 · z bliska: pozioma wstega (desktop pin + scrub, dotyk natywny), licznik, miernik, strzalki, lightbox
     4 · uslugi: desktop lusterko z podgladem jedzie za aktywnym wierszem; telefon kolo otwiera sie przy wejsciu wiersza
     5 · o mnie: kurtyny rozsuwaja sie nad kolazem, formy sie ukladaja, podpis literami + kreska
     6 · opinie: fragmenty i cytaty w dwoch paskach w przeciwne strony (cytaty tylko od 768 px)
     7 · przejscia miedzy sekcjami: kolo lusterka (clip-path jednolitej warstwy), plynna zmiana koloru (krycie), kartka (sticky)
     8 · slowo konturem (przerywnik) przesuwa sie z przewijaniem
     9 · naglowki w maskach (SplitText, linie) i kreski numerow, przyciski za kursorem (tylko precyzyjny wskaznik) */
(function () {
  'use strict';
  var d = document, W = window, root = d.documentElement;
  var $ = function (s, w) { return (w || d).querySelector(s); };
  var $$ = function (s, w) { return [].slice.call((w || d).querySelectorAll(s)); };
  var G = W.gsap, ST = W.ScrollTrigger, Split = W.SplitText, Draw = W.DrawSVGPlugin;
  var param = new URLSearchParams(location.search);
  var LITE = root.classList.contains('lite') || /Instagram/i.test(navigator.userAgent) || param.get('lite') === '1';
  var spokoj = function () { return W.matchMedia('(prefers-reduced-motion: reduce)').matches; };
  var mm = null, ostrzezono = false;
  var tryb = { ruch: false, pin: false };
  var BLANK = 'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==';

  if (!d.querySelector('[data-scene="kontakt"]')) return;          /* to nie jest pelna strona (np. sam prototyp hero) */
  root.classList.add('sk');

  function ostrzez(e) {
    if (ostrzezono) return;
    ostrzezono = true;
    try { console.warn('[sekcje] ruch wylaczony, zostaje wersja statyczna:', e && e.message ? e.message : e); } catch (_) {}
  }

  /* ── 0a · Lenis z hero: nie tworzymy drugiej instancji; referencje bierzemy z pierwszego zdarzenia scroll (emit jest w prototypie) ── */
  var lenisRef = null;
  try {
    var L = W.Lenis;
    if (L && L.prototype && typeof L.prototype.emit === 'function' && !L.prototype.__sekcje) {
      var emit0 = L.prototype.emit;
      L.prototype.emit = function () { lenisRef = this; return emit0.apply(this, arguments); };
      L.prototype.__sekcje = true;
    }
  } catch (_) {}
  function lenis() { return lenisRef && root.classList.contains('lenis') ? lenisRef : null; }
  function przewinDo(y, gladko, gotowe) {
    var l = lenis();
    if (l && gladko) l.scrollTo(y, { duration: 1.1, force: true, onComplete: gotowe });
    else { W.scrollTo({ top: y, behavior: gladko ? 'smooth' : 'instant' }); if (gotowe) gotowe(); }
  }

  /* ── 0b · lightbox (dziala tez bez GSAP; bez JS link otwiera sam plik zdjecia) ── */
  (function lightbox() {
    var dlg = $('[data-lb-okno]');
    var linki = $$('a[data-lb]');
    if (!dlg || !linki.length || typeof dlg.showModal !== 'function') return;
    var podpis = $('[data-lb-podpis]', dlg), i = 0, otwierajacy = null, x0 = null;
    var img = d.createElement('img');                              /* obraz powstaje dopiero z JS: bez JS okno i tak sie nie otwiera */
    img.decoding = 'async'; img.alt = '';
    podpis.parentNode.insertBefore(img, podpis);
    var dwie = function (n) { return (n < 10 ? '0' : '') + n; };
    function pokaz(n) {
      i = (n + linki.length) % linki.length;
      var a = linki[i], t = $('img', a);
      img.src = a.getAttribute('href');
      img.alt = t ? t.alt : '';
      podpis.textContent = dwie(i + 1) + ' / ' + dwie(linki.length);
    }
    linki.forEach(function (a, n) {
      a.addEventListener('click', function (e) {
        if (e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        otwierajacy = a;
        pokaz(n);
        dlg.showModal();
        root.classList.add('lb-otwarty');
        var l = lenis(); if (l) l.stop();
      });
    });
    $('[data-lb-zamknij]', dlg).addEventListener('click', function () { dlg.close(); });
    $('[data-lb-wstecz]', dlg).addEventListener('click', function () { pokaz(i - 1); });
    $('[data-lb-dalej]', dlg).addEventListener('click', function () { pokaz(i + 1); });
    dlg.addEventListener('click', function (e) { if (e.target === dlg) dlg.close(); });
    dlg.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') { e.preventDefault(); pokaz(i - 1); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); pokaz(i + 1); }
    });
    dlg.addEventListener('touchstart', function (e) { x0 = e.touches[0].clientX; }, { passive: true });
    dlg.addEventListener('touchend', function (e) {
      if (x0 === null) return;
      var dx = e.changedTouches[0].clientX - x0; x0 = null;
      if (Math.abs(dx) > 48) pokaz(i + (dx < 0 ? 1 : -1));
    }, { passive: true });
    dlg.addEventListener('close', function () {
      root.classList.remove('lb-otwarty');
      var l = lenis(); if (l) l.start();
      img.src = BLANK;
      if (otwierajacy) otwierajacy.focus({ preventScroll: true });
    });
  })();

  /* ── 0c · staly przycisk i staly spis: pojawiaja sie po wyjsciu z hero. Ktora sekcja jest pod danym punktem ekranu,
     mowi elementFromPoint (dziala tez, gdy sekcja-kartka lezy na przyklejonej poprzedniej). Przycisk chowa sie przy
     przyciskach z ta sama akcja (data-dok="ukryj"); spis pokazuje numer i nazwe biezacej sekcji, po stuknieciu liste skrotow ── */
  var spisRef = { zamknij: function () {} };
  (function staleElementy() {
    var dok = $('[data-anim="dok"]'), spis = $('[data-anim="spis-staly"]');
    if (!('IntersectionObserver' in W) || (!dok && !spis)) return;
    var hero = $('#hero'), poHero = !hero, poOkladce = !hero, widoczne = [];
    var pigulka = spis && $('.spis-pigulka', spis), lista = spis && $('.spis-lista', spis);
    var nrEl = spis && $('[data-spis-nr]', spis), tytEl = spis && $('[data-spis-tyt]', spis);
    var skroty = lista ? $$('[data-skrot]', lista) : [];
    var poId = {};
    skroty.forEach(function (a) { poId[a.getAttribute('data-skrot')] = a; });
    /* sekcje bez wlasnego miejsca w spisie wskazuja na sasiednia */
    var ZAMIANY = { 'pasek': null, 'z-bliska': 'prace', 'stopka': 'kontakt' };
    var biezacy = null, raf = 0;
    function sekcjaW(y) {
      var el = d.elementFromPoint(W.innerWidth / 2, y);
      return el && el.closest ? el.closest('[data-sekcja]') : null;
    }
    function stan() {
      raf = 0;
      if (dok) {
        dok.classList.toggle('widoczny', poHero && widoczne.length === 0);
        var dol = sekcjaW(W.innerHeight - 40);
        if (dol) dok.classList.toggle('na-jasnym', dol.getAttribute('data-nav') === 'light');
      }
      if (spis) {
        spis.classList.toggle('widoczny', poOkladce);           /* dopiero gdy okladka ze spisem prawie zniknela */
        var gora = sekcjaW(Math.min(W.innerHeight * 0.38, 320));
        if (gora) {
          var id = gora.getAttribute('data-sekcja');
          if (id in ZAMIANY) id = ZAMIANY[id] || (skroty[0] && skroty[0].getAttribute('data-skrot'));
          var a = poId[id];
          if (a && a !== biezacy) {
            if (biezacy) biezacy.removeAttribute('aria-current');
            biezacy = a;
            a.setAttribute('aria-current', 'true');
            nrEl.textContent = $('.skrot-nr', a).textContent;
            tytEl.textContent = $('.skrot-tyt', a).textContent;
          }
        }
        var wierzch = sekcjaW(30);
        if (wierzch) spis.classList.toggle('na-ciemnym', wierzch.getAttribute('data-nav') === 'dark');
      }
    }
    function zaplanuj() { if (!raf) raf = requestAnimationFrame(stan); }
    if (hero) {
      new IntersectionObserver(function (w) { poHero = !w[0].isIntersecting; zaplanuj(); }, { rootMargin: '-50% 0px 0px 0px' }).observe(hero);
      new IntersectionObserver(function (w) { poOkladce = !w[0].isIntersecting; zaplanuj(); }, { rootMargin: '-88% 0px 0px 0px' }).observe(hero);
    }
    if (dok) {
      var io = new IntersectionObserver(function (w) {
        w.forEach(function (e) {
          var k = widoczne.indexOf(e.target);
          if (e.isIntersecting && k < 0) widoczne.push(e.target);
          if (!e.isIntersecting && k >= 0) widoczne.splice(k, 1);
        });
        zaplanuj();
      });
      $$('[data-dok="ukryj"]').forEach(function (k) { io.observe(k); });
    }
    W.addEventListener('scroll', zaplanuj, { passive: true });
    W.addEventListener('resize', zaplanuj, { passive: true });
    zaplanuj();

    if (!spis || !pigulka || !lista) return;
    var otwarta = false;
    function zamknij(fokus) {
      if (!otwarta) return;
      otwarta = false;
      lista.hidden = true;
      pigulka.setAttribute('aria-expanded', 'false');
      var l = lenis(); if (l) l.start();
      d.removeEventListener('pointerdown', naZewnatrz, true);
      W.removeEventListener('wheel', zamknijTeraz, { passive: true });
      W.removeEventListener('touchmove', zamknijTeraz, { passive: true });
      if (fokus) pigulka.focus({ preventScroll: true });
    }
    function zamknijTeraz() { zamknij(false); }
    function naZewnatrz(e) { if (!spis.contains(e.target)) zamknij(false); }
    function otworz() {
      otwarta = true;
      lista.hidden = false;
      pigulka.setAttribute('aria-expanded', 'true');
      var l = lenis(); if (l) l.stop();
      d.addEventListener('pointerdown', naZewnatrz, true);
      W.addEventListener('wheel', zamknijTeraz, { passive: true });
      W.addEventListener('touchmove', zamknijTeraz, { passive: true });
      if (tryb.ruch && G) G.fromTo(lista, { opacity: 0, y: -8 }, { opacity: 1, y: 0, duration: 0.32, ease: 'power3.out', clearProps: 'opacity,transform' });
      (biezacy || skroty[0]).focus({ preventScroll: true });
    }
    pigulka.addEventListener('click', function () { if (otwarta) zamknij(true); else otworz(); });
    spis.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && otwarta) { e.preventDefault(); zamknij(true); }
      if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && otwarta) {
        e.preventDefault();
        var k = skroty.indexOf(d.activeElement);
        skroty[(k + (e.key === 'ArrowDown' ? 1 : -1) + skroty.length) % skroty.length].focus();
      }
    });
    lista.addEventListener('click', function (e) { if (e.target.closest('a')) zamknij(false); });
    spis.addEventListener('focusout', function (e) { if (otwarta && !spis.contains(e.relatedTarget)) zamknij(false); });
    spisRef.zamknij = zamknij;
  })();

  /* ── 0d · kotwice w sekcjach i w stalym spisie: Lenis, jesli jest; odstep na staly spis u gory; fokus na celu.
     Kotwice w #hero (spis okladki, pomijanie sceny) obsluguje main.js ── */
  d.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('a[href^="#"]');
    if (!a || e.defaultPrevented || e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || a.closest('#hero')) return;
    var h = a.getAttribute('href'), cel = null;
    if (!h || h.length < 2) return;
    try { cel = d.getElementById(decodeURIComponent(h.slice(1))); } catch (_) { return; }
    if (a.classList.contains('pomin') && h === '#uslugi') cel = d.getElementById('prace') || cel;   /* main.js kieruje pomijanie na Uslugi; pierwsza tresc po hero to galeria */
    if (!cel) return;
    e.preventDefault();
    var odstep = (cel.id === 'hero' || cel.hasAttribute('data-scene') && /galeria|wstega/.test(cel.getAttribute('data-scene'))) ? 0 : 72;
    /* przyklejona kartka (sticky) ma teraz inne polozenie niz w ukladzie: na chwile pomiaru zdejmujemy przyklejenie */
    var przyklejone = $$('.kartka-aktywna');
    przyklejone.forEach(function (k) { k.classList.toggle('kartka-aktywna', false); });
    var y = Math.max(0, cel.getBoundingClientRect().top + W.scrollY - (cel.id === 'hero' ? 0 : odstep));
    przyklejone.forEach(function (k) { k.classList.toggle('kartka-aktywna', true); });
    if (cel.id === 'hero') y = 0;
    przewinDo(y, tryb.ruch, function () {
      if (!cel.matches('a,button,input,summary,[tabindex]')) cel.setAttribute('tabindex', '-1');
      cel.focus({ preventScroll: true });
    });
    if (cel.id && location.hash !== '#' + cel.id) history.pushState(null, '', '#' + cel.id);
  });

  /* ── 0e · Dobrze wiedziec: plynne <details>. Wysokosc zmienia sie raz (bez animowania ukladu), tresc wchodzi kryciem i przesunieciem ── */
  $$('.faq-poz').forEach(function (poz) {
    var sum = $('summary', poz), odp = $('.faq-odp', poz);
    if (!sum || !odp) return;
    sum.addEventListener('click', function (e) {
      if (!G || !tryb.ruch) return;
      e.preventDefault();
      if (poz.open) {
        G.to(odp, { autoAlpha: 0, y: -6, duration: 0.18, ease: 'power1.in', overwrite: true,
          onComplete: function () { poz.open = false; G.set(odp, { clearProps: 'all' }); if (ST) ST.refresh(); } });
      } else {
        poz.open = true;
        G.fromTo(odp, { autoAlpha: 0, y: -10 }, { autoAlpha: 1, y: 0, duration: 0.42, ease: 'power3.out', overwrite: true,
          onComplete: function () { G.set(odp, { clearProps: 'all' }); } });
        if (ST) ST.refresh();
      }
    });
  });

  /* ── 0f · kontakt: puderniczka zamyka sie raz, gdy 60% jej miejsca jest w kadrze (WAAPI, 0,9 s). Bez ruchu i w Instagramie: zamknieta ── */
  function kontakt() {
    var kp = $('[data-anim="kp"]'), panel = kp && $('[data-anim="kp-panel"]', kp);
    if (!kp || !panel) return;
    if (spokoj() || LITE || !('IntersectionObserver' in W) || !panel.animate) { kp.classList.add('zamknieta'); return; }
    kp.classList.add('kp-ruch');
    /* rozgrzewka poltora ekranu wczesniej: warstwy puderniczki pobrane i zdekodowane poza watkiem glownym, zanim ruszy obrot
       (pomiar przy CPU 4x: start animacji na niezdekodowanych warstwach dawal pojedyncza klatke 120-190 ms) */
    var rozgrzej = new IntersectionObserver(function (w) {
      if (!w.some(function (x) { return x.isIntersecting; })) return;
      rozgrzej.disconnect();
      $$('img', kp).forEach(function (im) { im.loading = 'eager'; if (im.decode) im.decode().catch(function () {}); });
    }, { rootMargin: '0px 0px 150% 0px' });
    rozgrzej.observe(kp);
    var io = new IntersectionObserver(function (w) {
      if (!w.some(function (x) { return x.isIntersecting; })) return;
      io.disconnect();
      requestAnimationFrame(function () {
        var a = panel.animate([{ transform: 'rotateX(125deg)' }, { transform: 'rotateX(0deg)' }],
          { duration: 900, easing: 'cubic-bezier(0.45, 0, 0.55, 1)', fill: 'forwards' });
        a.onfinish = function () { kp.classList.add('zamknieta'); a.cancel(); };
      });
    }, { threshold: 0.6 });
    io.observe(kp);
  }
  kontakt();

  if (!G || !ST) return;                                         /* bez bibliotek: zostaje stan statyczny z CSS */
  try {
    G.registerPlugin(ST);
    if (Split) G.registerPlugin(Split);
    if (Draw) G.registerPlugin(Draw);
  } catch (e) { ostrzez(e); return; }

  /* ── 1 · petla paska: klon grupy (aria-hidden), xPercent -50 w kolko; predkosc i kierunek z przewijania ── */
  function petla(el, o) {
    var tor = $('.pasek-tor', el), grupa = tor && $('.pasek-grupa', tor);
    if (!tor || !grupa || !grupa.children.length) return null;
    var dodane = [], baza = [].slice.call(grupa.children), cel = Math.max(el.clientWidth, 1400), ochrona = 0;
    el.classList.add('w-ruchu');
    while (grupa.scrollWidth < cel && ochrona++ < 8) {
      baza.forEach(function (n) { var k = n.cloneNode(true); k.setAttribute('aria-hidden', 'true'); grupa.appendChild(k); dodane.push(k); });
    }
    var kopia = grupa.cloneNode(true);
    kopia.setAttribute('aria-hidden', 'true');
    $$('a, button', kopia).forEach(function (x) { x.setAttribute('tabindex', '-1'); });
    tor.appendChild(kopia);
    dodane.push(kopia);
    var kier = o.kierunek || -1;
    var dl = Math.max(12, grupa.offsetWidth / (o.predkosc || 40));
    var tw = G.fromTo(tor, { xPercent: kier < 0 ? 0 : -50 }, { xPercent: kier < 0 ? -50 : 0, duration: dl, ease: 'none', repeat: -1, paused: true });
    tw.totalTime(dl * 400);                                       /* zapas w tyl, zeby odwrocenie kierunku nie dobilo do zera */
    var widoczny = false, wstrzymany = false, boost = 0, kierS = 1, skala = 1;
    function sync() { if (widoczny && !wstrzymany) tw.resume(); else tw.pause(); }
    var st = ST.create({
      trigger: el, start: 'top bottom', end: 'bottom top',
      onToggle: function (s) { widoczny = s.isActive; sync(); },
      onUpdate: o.reaguj ? function (s) { boost = Math.min(4, Math.abs(s.getVelocity()) / 650); kierS = s.direction || 1; } : null
    });
    var tick = function () {
      if (!widoczny || wstrzymany) return;
      boost *= 0.93;
      var c = (1 + boost) * (o.odwracaj ? kierS : 1);
      skala += (c - skala) * 0.1;
      tw.timeScale(Math.abs(skala) < 0.05 ? (skala < 0 ? -0.05 : 0.05) : skala);
    };
    if (o.reaguj) G.ticker.add(tick);
    var stop = function () { wstrzymany = true; sync(); }, start = function () { wstrzymany = false; sync(); };
    if (o.pauza) {
      el.addEventListener('pointerenter', stop); el.addEventListener('pointerleave', start);
      el.addEventListener('focusin', stop); el.addEventListener('focusout', start);
    }
    return function () {
      G.ticker.remove(tick); st.kill(); tw.kill();
      if (o.pauza) {
        el.removeEventListener('pointerenter', stop); el.removeEventListener('pointerleave', start);
        el.removeEventListener('focusin', stop); el.removeEventListener('focusout', start);
      }
      dodane.forEach(function (n) { n.remove(); });
      el.classList.remove('w-ruchu');
      G.set(tor, { clearProps: 'transform' });
    };
  }

  function pasek(c) {
    var el = $('.tasma[data-anim="petla"]');
    return el ? petla(el, { predkosc: c.szeroki ? 52 : 34, kierunek: -1, reaguj: !LITE, odwracaj: !LITE }) : null;
  }

  /* ── 2 · galeria luster: przod wlatuje z bliska (duza skala, z zewnatrz), tyl wychodzi z glebi (mala skala, od srodka) ── */
  function galeria(c) {
    var scena = $('[data-anim="galeria-scena"]');
    if (!scena) return null;
    var lustra = $$('[data-anim="gl-lustro"]', scena);
    var linie = $$('.galeria-h2 .maska > span', scena);
    if (!lustra.length) return null;
    var wektor = function (el) {       /* srodek lusterka wzgledem srodka sceny; z ukladu (offset*), wiec niezalezny od transformacji */
      return { x: el.offsetLeft + el.offsetWidth / 2 - scena.clientWidth / 2, y: el.offsetTop + el.offsetHeight / 2 - scena.clientHeight / 2 };
    };
    var rot = function (el) { return parseFloat(getComputedStyle(el).getPropertyValue('--rot')) || 0; };
    var pin = c.pin, k = pin ? 1 : 0.7, przypiecie = null;
    /* desktop: osobny trigger tylko do przypiecia (150% ekranu), a os rusza juz przy wjezdzie sceny (top 85%), zeby
       wjezdzajaca scena nie byla pusta; przypiecie tworzymy pierwsze, wiec koniec osi uwzglednia jego dlugosc */
    if (pin && !LITE) {
      przypiecie = ST.create({ trigger: scena, pin: true, start: 'top top', end: function () { return '+=' + Math.round(W.innerHeight * 1.5); },
        anticipatePin: 1, invalidateOnRefresh: true,
        onToggle: function (s) { G.set(lustra, { willChange: s.isActive ? 'transform, opacity' : 'auto' }); } });
    }
    var tl = G.timeline({
      defaults: { ease: 'none' },
      paused: LITE,
      scrollTrigger: LITE ? null : (pin
        ? { trigger: scena, start: 'top 85%', end: function () { return '+=' + Math.round(W.innerHeight * (0.85 + 1.5)); },
            scrub: 0.6, invalidateOnRefresh: true }
        : { trigger: scena, start: 'top 82%', end: 'center 52%', scrub: 0.5, invalidateOnRefresh: true })
    });
    tl.addLabel('naglowek', 0);
    if (linie.length) tl.fromTo(linie, { yPercent: 112 }, { yPercent: 0, duration: 1.6, stagger: 0.3, ease: 'power3.out' }, 0);
    tl.addLabel('lustra', 0.4);
    lustra.forEach(function (el, i) {
      var przod = el.getAttribute('data-glebia') === 'przod', r = rot(el), s = (i % 2 ? 1 : -1);
      tl.fromTo(el,
        przod
          ? { x: function () { return wektor(el).x * 0.85 * k; }, y: function () { return wektor(el).y * 0.85 * k + 60; },
              scale: pin ? 2.1 : 1.4, rotation: r + s * 12, autoAlpha: 0 }
          : { x: function () { return -wektor(el).x * 0.5 * k; }, y: function () { return -wektor(el).y * 0.5 * k; },
              scale: pin ? 0.34 : 0.5, rotation: r - s * 10, autoAlpha: 0 },
        { x: 0, y: 0, scale: 1, rotation: r, autoAlpha: 1, duration: 3, ease: 'power2.out', immediateRender: true },
        0.4 + i * 0.3);
    });
    tl.addLabel('komplet');
    if (pin) {                                                      /* oddech: warstwy rozjezdzaja sie lekko w roznym tempie */
      var przodEl = lustra.filter(function (el) { return el.getAttribute('data-glebia') === 'przod'; });
      var tylEl = lustra.filter(function (el) { return el.getAttribute('data-glebia') !== 'przod'; });
      tl.to(przodEl, { y: '-=26', duration: 2.2 }, 'komplet');
      if (tylEl.length) tl.to(tylEl, { y: '+=12', duration: 2.2 }, 'komplet');
      if (linie.length) tl.to(linie, { yPercent: -6, duration: 2.2 }, 'komplet');
    }
    if (LITE) ST.create({ trigger: scena, start: 'top 75%', once: true, onEnter: function () { tl.duration(1.8); tl.play(0); } });
    /* tylko wlasciwosci ruchu: "all" skasowaloby tez --x/--y/--w/--rot z atrybutu style (polozenie lusterek) */
    return function () { tl.kill(); if (przypiecie) przypiecie.kill(true); G.set(lustra.concat(linie), { clearProps: 'transform,opacity,visibility,willChange' }); };
  }

  /* ── 3 · z bliska: desktop pin i przesuniecie w poziomie; dotyk natywny (pionowego scrolla nie przejmujemy) ── */
  function wstega(c) {
    var scena = $('[data-anim="wstega-scena"]');
    if (!scena) return null;
    var okno = $('[data-anim="wstega-okno"]', scena), tor = $('[data-anim="wstega-tor"]', scena);
    var prace = $$('.praca', tor), licznik = $('[data-licznik]', scena), miernik = $('[data-miernik]', scena);
    var wstecz = $('[data-wstecz]', scena), dalej = $('[data-dalej]', scena);
    if (!okno || !tor || !prace.length) return null;
    var sprz = [], biez = -1, n = prace.length, tl = null;
    var ustaw = function (i) {
      i = Math.max(0, Math.min(n - 1, i));
      if (i === biez) return;
      biez = i;
      if (licznik) licznik.textContent = (i < 9 ? '0' : '') + (i + 1);
      if (wstecz) wstecz.disabled = i === 0;
      if (dalej) dalej.disabled = i === n - 1;
    };
    var odl = function () { return Math.max(0, tor.scrollWidth - okno.clientWidth); };
    ustaw(0);
    if (c.pin && odl() > 40) {
      var obrazy = $$('.praca-rama img', tor);
      tl = G.timeline({
        defaults: { ease: 'none' },
        scrollTrigger: {
          trigger: scena, pin: true, start: 'top top', end: function () { return '+=' + Math.max(odl(), Math.round(W.innerHeight * 0.8)); },
          scrub: 0.6, anticipatePin: 1, invalidateOnRefresh: true,
          onUpdate: function (s) { ustaw(Math.round(s.progress * (n - 1))); }
        }
      });
      tl.to(tor, { x: function () { return -odl(); }, duration: 1 }, 0);
      if (obrazy.length) tl.fromTo(obrazy, { xPercent: -5 }, { xPercent: 5, duration: 1 }, 0);
      if (miernik) tl.fromTo(miernik, { scaleX: 0 }, { scaleX: 1, duration: 1 }, 0);
      var doPracy = function (i, natychmiast) {
        var st = tl.scrollTrigger;
        var u = Math.max(0, Math.min(1, (prace[i].offsetLeft - prace[0].offsetLeft) / Math.max(1, odl())));
        przewinDo(st.start + (st.end - st.start) * u, !natychmiast && tryb.ruch);
      };
      var fokus = function (e) { var p = e.target.closest('.praca'); if (p) doPracy(prace.indexOf(p), true); };
      tor.addEventListener('focusin', fokus);
      sprz.push(function () { tor.removeEventListener('focusin', fokus); });
      var klik = function (kier) { return function () { var i = Math.max(0, Math.min(n - 1, biez + kier)); doPracy(i); }; };
      var kw = klik(-1), kd = klik(1);
      if (wstecz) wstecz.addEventListener('click', kw);
      if (dalej) dalej.addEventListener('click', kd);
      sprz.push(function () { if (wstecz) wstecz.removeEventListener('click', kw); if (dalej) dalej.removeEventListener('click', kd); });
    } else {
      var raf = 0;
      var naScroll = function () {
        if (raf) return;
        raf = requestAnimationFrame(function () {
          raf = 0;
          var maks = Math.max(1, okno.scrollWidth - okno.clientWidth), p = okno.scrollLeft / maks;
          if (miernik) miernik.style.transform = 'scaleX(' + Math.max(0, Math.min(1, p)).toFixed(3) + ')';
          ustaw(Math.round(p * (n - 1)));
        });
      };
      okno.addEventListener('scroll', naScroll, { passive: true });
      var skok = function (kier) {
        return function () {
          var i = Math.max(0, Math.min(n - 1, biez + kier));
          okno.scrollTo({ left: prace[i].offsetLeft - prace[0].offsetLeft, behavior: tryb.ruch ? 'smooth' : 'instant' });
        };
      };
      var sw = skok(-1), sd = skok(1);
      if (wstecz) wstecz.addEventListener('click', sw);
      if (dalej) dalej.addEventListener('click', sd);
      naScroll();
      sprz.push(function () {
        okno.removeEventListener('scroll', naScroll);
        if (wstecz) wstecz.removeEventListener('click', sw);
        if (dalej) dalej.removeEventListener('click', sd);
        if (miernik) miernik.style.transform = '';
      });
    }
    return function () { if (tl) tl.kill(); G.set([tor].concat($$('.praca-rama img', tor)), { clearProps: 'transform' }); sprz.forEach(function (f) { f(); }); biez = -1; };
  }

  /* ── 4 · uslugi ── */
  function uslugi(c) {
    var lista = $('[data-anim="uslugi-lista"]');
    if (!lista) return null;
    var wiersze = $$('[data-usluga]', lista), podglad = $('[data-anim="podglad"]', lista);
    if (!wiersze.length) return null;
    var sprz = [];
    if (c.pin && podglad && getComputedStyle(podglad).display !== 'none') {
      var obrazy = $$('img', podglad), lustro = $('.podglad-lustro', podglad), aktywny = -1;
      var qy = G.quickTo(podglad, 'y', { duration: 0.75, ease: 'power3.out' });
      var polozenie = function (i) {
        var w = wiersze[i], h = podglad.offsetHeight;
        var naglowek = $('.usluga-wiersz, summary', w) || w;
        var y = w.offsetTop + naglowek.offsetHeight / 2 - h / 2;
        return Math.max(0, Math.min(lista.clientHeight - h, y));
      };
      var ustaw = function (i, wymus) {
        if (i === aktywny && !wymus) return;
        var zmiana = i !== aktywny;
        aktywny = i;
        wiersze.forEach(function (w, k) { w.classList.toggle('aktywna', k === i); });
        if (zmiana) {
          obrazy.forEach(function (im, k) { im.classList.toggle('widoczny', k === Math.min(i, obrazy.length - 1)); });
          G.fromTo(lustro, { scale: 0.94, rotation: -3 }, { scale: 1, rotation: 0, duration: 0.7, ease: 'power3.out', overwrite: true });
        }
        qy(polozenie(i));
      };
      G.set(podglad, { y: polozenie(0) });
      ustaw(0, true);
      wiersze.forEach(function (w, i) {
        var stw = ST.create({ trigger: w, start: 'top 58%', end: 'bottom 58%', onToggle: function (s) { if (s.isActive) ustaw(i); } });
        sprz.push(function () { stw.kill(); });
        var wej = function () { lista.classList.add('hover'); ustaw(i); };
        w.addEventListener('mouseenter', wej); w.addEventListener('focusin', wej);
        sprz.push(function () { w.removeEventListener('mouseenter', wej); w.removeEventListener('focusin', wej); });
      });
      var wyj = function () { lista.classList.remove('hover'); };
      lista.addEventListener('mouseleave', wyj);
      var odswiez = 0, zmiana = function () { clearTimeout(odswiez); odswiez = setTimeout(function () { ST.refresh(); ustaw(Math.max(0, aktywny), true); }, 60); };
      wiersze.forEach(function (w) { if (w.tagName === 'DETAILS') w.addEventListener('toggle', zmiana); });
      sprz.push(function () {
        lista.removeEventListener('mouseleave', wyj); lista.classList.remove('hover');
        wiersze.forEach(function (w) { w.classList.remove('aktywna'); if (w.tagName === 'DETAILS') w.removeEventListener('toggle', zmiana); });
        G.set([podglad, lustro], { clearProps: 'transform' });
      });
    } else {
      /* telefon i tablet: okragla ramka otwiera sie jak lusterko (skala ramki 0,12 -> 1, zdjecie 1,7 -> 1) */
      wiersze.forEach(function (w) {
        var l = $('.usluga-lustro', w), im = l && $('img', l);
        if (!l || !im) return;
        var t = G.timeline({ paused: true })
          .fromTo(l, { scale: 0.12 }, { scale: 1, duration: 0.95, ease: 'power3.out' }, 0)
          .fromTo(im, { scale: 1.7 }, { scale: 1, duration: 1.25, ease: 'power3.out' }, 0);
        var st = ST.create({ trigger: w, start: 'top 84%', once: true, onEnter: function () { t.play(); } });
        sprz.push(function () { st.kill(); t.kill(); G.set([l, im], { clearProps: 'transform' }); });
      });
    }
    return function () { sprz.forEach(function (f) { f(); }); };
  }

  /* ── 5 · o mnie: kurtyny nad kolazem, formy ukladaja sie; podpis literami i kreska (DrawSVG) ── */
  function oMnie(c) {
    var plansza = $('[data-anim="plansza"]');
    var sprz = [];
    if (plansza) {
      var kurtyny = $$('.kurtyna', plansza), om = $$('.om', plansza);
      var rot = function (el) { return parseFloat(getComputedStyle(el).getPropertyValue('--rot')) || 0; };
      var t;
      // telefon i tablet: bez kurtyn (sekcja wjezdza jako kartka na cennik i zakryty kolaz wygladal jak pusty pas); formy od razu przy wejsciu
      if (LITE || !kurtyny.length || !c.pin) {
        t = G.timeline({ paused: true }).fromTo(om, { autoAlpha: 0, y: 24, scale: 0.96 }, { autoAlpha: 1, y: 0, scale: 1, duration: 0.7, stagger: 0.1, ease: 'power3.out' });
        var st0 = ST.create({ trigger: plansza, start: 'top 96%', once: true, onEnter: function () { t.play(); } });
        sprz.push(function () { st0.kill(); });
      } else {
        t = G.timeline({
          paused: !c.pin,
          scrollTrigger: c.pin ? { trigger: plansza, start: 'top 82%', end: 'top 18%', scrub: 0.5 } : null
        });
        t.fromTo(kurtyny, { xPercent: 0 }, { xPercent: function (i) { return i ? 102 : -102; }, duration: 1, ease: 'power2.inOut' }, 0);
        om.forEach(function (el, i) {
          var r = rot(el);
          t.fromTo(el, { scale: 1.14, rotation: r + (i % 2 ? 7 : -7) }, { scale: 1, rotation: r, duration: 1.1, ease: 'power2.out' }, 0.1 + i * 0.06);
        });
        if (!c.pin) {
          t.duration(1.3);
          var st1 = ST.create({ trigger: plansza, start: 'top 72%', once: true, onEnter: function () { t.play(); } });
          sprz.push(function () { st1.kill(); });
        }
      }
      sprz.push(function () { t.kill(); G.set(kurtyny.concat(om), { clearProps: 'transform,opacity,visibility' }); });
    }
    var podpis = $('[data-anim="podpis"]'), napis = podpis && $('.podpis-tekst', podpis), kreska = podpis && $('[data-anim="podpis-kreska"]', podpis);
    if (podpis && napis) {
      var tp = G.timeline({ paused: true }), sp = null;
      if (Split) {
        sp = Split.create(napis, { type: 'words,chars', charsClass: 'znak' });
        tp.from(sp.chars, { autoAlpha: 0, yPercent: 35, rotation: -6, duration: 0.6, stagger: 0.06, ease: 'power3.out' }, 0);
      } else tp.from(napis, { autoAlpha: 0, y: 12, duration: 0.6 }, 0);
      if (kreska) tp.fromTo(kreska, Draw ? { drawSVG: '0% 0%' } : { autoAlpha: 0 }, Draw ? { drawSVG: '0% 100%', duration: 0.8, ease: 'power2.inOut' } : { autoAlpha: 1, duration: 0.4 }, '-=0.25');
      var st2 = ST.create({ trigger: podpis, start: 'top 88%', once: true, onEnter: function () { tp.play(); } });
      sprz.push(function () { st2.kill(); tp.kill(); if (sp) sp.revert(); if (kreska) G.set(kreska, { clearProps: 'all' }); });
    }
    return function () { sprz.forEach(function (f) { f(); }); };
  }

  /* ── 6 · opinie: fragmenty w lewo (zawsze przy ruchu), pelne cytaty w prawo (od 768 px, min. 2 cytaty) ── */
  function opinie(c) {
    var sprz = [];
    var fr = $('.opinie-fragmenty[data-anim="petla"]');
    if (fr) sprz.push(petla(fr, { predkosc: c.szeroki ? 64 : 38, kierunek: -1, reaguj: !LITE, odwracaj: false }));
    var cy = $('[data-anim="petla-cytaty"]');
    if (cy && c.szeroki && !LITE && $$('.cytat', cy).length >= 2) sprz.push(petla(cy, { predkosc: 30, kierunek: 1, reaguj: true, pauza: true }));
    return function () { sprz.forEach(function (f) { if (f) f(); }); };
  }

  /* ── 7 · przejscia miedzy sekcjami. Warstwa .przejscie: kolor poprzedniej sekcji na gornych 100svh nowej (z CSS, tylko przy ruchu).
     kolo: kolo w kolorze nowej sekcji (z jej faktura) rosnie od srodka gornej krawedzi, za nim cienka obraczka w kolorze wyroznienia
           (motyw lusterka); animujemy clip-path dwoch jednolitych warstw, nie tresc, wiec malowanie jest tanie
     plynnie: warstwa w kolorze poprzedniej sekcji gasnie (krycie): tlo przechodzi z jednego koloru w drugi
     kartka: poprzednia sekcja przykleja sie dolna krawedzia (sticky, top = wys. ekranu - wys. sekcji), nowa nachodzi na nia
             z cieniem jak kolejna kartka magazynu, a przyklejona przygasa ── */
  function przejscia(c) {
    var sprz = [];
    $$('[data-przejscie]').forEach(function (sek) {
      var typ = sek.getAttribute('data-przejscie'), w = $('.przejscie', sek);
      if (typ === 'kolo' && w) {
        var kolo = $('.przejscie-kolo', w), rama = $('.przejscie-rama', w), R = 1, stan = { p: 0 };
        var mierz = function () { R = Math.hypot(w.offsetWidth / 2, w.offsetHeight) + 8; };
        var rysuj = function () {
          var r = R * stan.p;
          kolo.style.clipPath = 'circle(' + r.toFixed(1) + 'px at 50% 0px)';
          rama.style.clipPath = 'circle(' + (r > 0.5 ? r + (c.szeroki ? 7 : 5) : 0).toFixed(1) + 'px at 50% 0px)';
          w.style.visibility = stan.p >= 0.999 ? 'hidden' : '';
        };
        mierz();
        var tw = G.to(stan, { p: 1, ease: 'sine.inOut', onUpdate: rysuj,
          scrollTrigger: { trigger: sek, start: 'top bottom', end: 'top 10%', scrub: LITE ? true : 0.35, onRefresh: function () { mierz(); rysuj(); } } });
        rysuj();
        sprz.push(function () { tw.kill(); kolo.style.clipPath = rama.style.clipPath = w.style.visibility = ''; });
      } else if (typ === 'plynnie' && w) {
        var tp = G.fromTo(w, { opacity: 1 }, { opacity: 0, ease: 'none',
          scrollTrigger: { trigger: sek, start: 'top 92%', end: 'top 22%', scrub: true } });
        sprz.push(function () { tp.kill(); G.set(w, { clearProps: 'opacity,visibility' }); });
      } else if (typ === 'kartka') {
        var pod = sek.previousElementSibling;
        while (pod && !pod.hasAttribute('data-kartka-pod')) pod = pod.previousElementSibling;
        if (!pod) return;
        var cien = d.createElement('div');
        cien.className = 'kartka-cien';
        cien.setAttribute('aria-hidden', 'true');
        pod.appendChild(cien);
        var ustawTop = function () { pod.style.setProperty('--kartka-top', Math.min(0, W.innerHeight - pod.offsetHeight) + 'px'); };
        ustawTop();
        pod.classList.add('kartka-aktywna');
        /* pomiary ScrollTrigger przy naturalnym ukladzie: na czas refresh sticky schodzi, potem wraca */
        var przed = function () { pod.classList.remove('kartka-aktywna'); };
        var po = function () { ustawTop(); pod.classList.add('kartka-aktywna'); };
        ST.addEventListener('refreshInit', przed);
        ST.addEventListener('refresh', po);
        var ro = 'ResizeObserver' in W ? new ResizeObserver(function () { ustawTop(); }) : null;
        if (ro) ro.observe(pod);
        var tk = G.fromTo(cien, { opacity: 0 }, { opacity: 0.45, ease: 'none',
          scrollTrigger: { trigger: sek, start: 'top bottom', end: 'top top', scrub: true } });
        sprz.push(function () {
          tk.kill(); cien.remove(); if (ro) ro.disconnect();
          ST.removeEventListener('refreshInit', przed); ST.removeEventListener('refresh', po);
          pod.classList.remove('kartka-aktywna'); pod.style.removeProperty('--kartka-top');
        });
      }
    });
    return function () { sprz.forEach(function (f) { f(); }); };
  }

  /* ── 8 · slowo konturem: przesuwa sie w poziomie razem z przewijaniem (ozdoba, tresc jest w naglowkach) ── */
  function przerywnik() {
    var el = $('[data-anim="przerywnik"]'), tor = el && $('.przerywnik-tor', el);
    if (!tor) return null;
    var tw = G.fromTo(tor, { xPercent: 4 }, { xPercent: -26, ease: 'none',
      scrollTrigger: { trigger: el, start: 'top bottom', end: 'bottom top', scrub: LITE ? true : 0.5 } });
    return function () { tw.kill(); G.set(tor, { clearProps: 'transform' }); };
  }

  /* ── 9a · naglowki sekcji wchodza liniami w maskach; kreska przy numerze sekcji rysuje sie od lewej ── */
  function naglowki() {
    var lista = $$('[data-split]');
    var sprz = [];
    lista.forEach(function (h) {
      if (Split) {
        var sp = Split.create(h, {
          type: 'lines', mask: 'lines', autoSplit: true, linesClass: 'sl',
          onSplit: function (self) {
            /* maski maja zapas na ogonki i kreski (CSS .sl-mask); po wejsciu zdejmujemy przyciecie calkiem */
            return G.from(self.lines, { yPercent: 118, duration: 0.95, stagger: 0.1, ease: 'power3.out',
              scrollTrigger: { trigger: h, start: 'top 88%', once: true },
              onComplete: function () { G.set(self.masks, { overflow: 'visible' }); } });
          }
        });
        sprz.push(function () { sp.revert(); });
      } else {
        var t = G.from(h, { autoAlpha: 0, y: 28, duration: 0.8, ease: 'power3.out', scrollTrigger: { trigger: h, start: 'top 88%', once: true } });
        sprz.push(function () { t.kill(); G.set(h, { clearProps: 'all' }); });
      }
    });
    $$('.nr').forEach(function (nr) {
      var linia = $('.nr-linia', nr), cyfra = $('.nr-cyfra', nr);
      if (!linia) return;
      var t = G.timeline({ scrollTrigger: { trigger: nr, start: 'top 90%', once: true } })
        .from(cyfra, { yPercent: 60, autoAlpha: 0, duration: 0.6, ease: 'power3.out' }, 0)
        .from(linia, { scaleX: 0, duration: 1.1, ease: 'power3.out' }, 0.1);
      sprz.push(function () { t.kill(); G.set([linia, cyfra], { clearProps: 'transform,opacity,visibility' }); });
    });
    return function () { sprz.forEach(function (f) { f(); }); };
  }

  /* ── 9b · przyciski za kursorem (tylko precyzyjny wskaznik) ── */
  function magnes() {
    if (!W.matchMedia('(hover: hover) and (pointer: fine)').matches) return null;
    var sprz = [];
    $$('main > section:not(#hero) .przycisk').forEach(function (b) {
      var qx = G.quickTo(b, 'x', { duration: 0.5, ease: 'power3.out' }), qy = G.quickTo(b, 'y', { duration: 0.5, ease: 'power3.out' });
      var ruch = function (e) { var r = b.getBoundingClientRect(); qx((e.clientX - r.left - r.width / 2) * 0.18); qy((e.clientY - r.top - r.height / 2) * 0.3); };
      var wyj = function () { qx(0); qy(0); };
      b.addEventListener('pointermove', ruch); b.addEventListener('pointerleave', wyj);
      sprz.push(function () { b.removeEventListener('pointermove', ruch); b.removeEventListener('pointerleave', wyj); G.set(b, { clearProps: 'transform' }); });
    });
    return function () { sprz.forEach(function (f) { f(); }); };
  }

  /* ── 10 · matchMedia: ruch / statyczny, pin od 1100 x 600 (poza Instagramem); przy zmianie trybu wszystko od nowa ── */
  function awaria(e) {
    ostrzez(e);
    setTimeout(function () {
      try { if (mm) mm.revert(); } catch (_) {}
      root.classList.remove('sk-ruch', 'sk-pin');
      tryb.ruch = tryb.pin = false;
    }, 0);
  }
  try {
    mm = G.matchMedia();
    mm.add({
      ruch: '(prefers-reduced-motion: no-preference)',
      pin: '(min-width: 1100px) and (min-height: 600px)',
      szeroki: '(min-width: 768px)',
      zawsze: 'all'
    }, function (ctx) {
      var c = { ruch: ctx.conditions.ruch, pin: ctx.conditions.pin && !LITE && ctx.conditions.ruch, szeroki: ctx.conditions.szeroki };
      tryb.ruch = c.ruch; tryb.pin = c.pin;
      spisRef.zamknij(false);
      root.classList.toggle('sk-ruch', c.ruch);
      root.classList.toggle('sk-pin', c.pin);
      if (!c.ruch) return function () { root.classList.remove('sk-ruch', 'sk-pin'); };
      var sprz = [];
      try {
        /* kolejnosc tworzenia = kolejnosc na stronie (piny przed tym, co pod nimi) */
        [pasek, galeria, wstega, uslugi, przejscia, przerywnik, oMnie, opinie, naglowki, magnes].forEach(function (f) {
          var s = f(c);
          if (typeof s === 'function') sprz.push(s);
        });
        ST.sort();
        root.setAttribute('data-sekcje', c.pin ? 'pin' : 'ruch');
      } catch (e) { awaria(e); }
      return function () {
        sprz.reverse().forEach(function (f) { try { f(); } catch (_) {} });
        root.classList.remove('sk-ruch', 'sk-pin');
        root.removeAttribute('data-sekcje');
      };
    });
  } catch (e) { awaria(e); }

  /* odswiezenie po krojach i zaladowaniu: main.js robi to sam, gdy jego scena dziala (data-animator) */
  var odswiez = function () { if (!root.hasAttribute('data-animator')) { try { ST.refresh(); } catch (_) {} } };
  if (d.fonts && d.fonts.ready) d.fonts.ready.then(odswiez);
  if (d.readyState === 'complete') odswiez(); else W.addEventListener('load', odswiez, { once: true });

  /* tylko do kontroli jakosci: stan scen */
  W.__SEKCJE__ = {
    stan: function () {
      return { ruch: tryb.ruch, pin: tryb.pin, lite: LITE, lenis: !!lenis(),
        triggery: ST.getAll().map(function (t) { return { id: t.trigger && (t.trigger.id || t.trigger.className), start: Math.round(t.start), end: Math.round(t.end), pin: !!t.pin }; }) };
    }
  };
})();
