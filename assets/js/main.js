/* main.js: ruch hero "Moment w lustrze" (GSAP 3.15 + ScrollTrigger, Lenis tylko na desktopie).
   Strona jest kompletna bez tego pliku: gdy czegos brakuje albo cos sie wysypie, zdejmujemy html.js
   i zostaje stan statyczny z CSS (otwarta puderniczka w przeplywie).

   Kontrakt z CSS i szablonem (naglowek assets/css/hero.css):
   - stan sceny dziala tylko przy html.js + prefers-reduced-motion: no-preference + wysokosc okna >= 501 px;
     te same warunki sprawdza tu gsap.matchMedia(), a przy zmianie trybu wszystko sie cofa i buduje od nowa;
   - zrodlem prawdy geometrii jest CSS: stany zamknieta / otwarta / koncowa odczytujemy z getComputedStyle
     (ustawiajac na chwile data-faza na .scena) i dopiero miedzy nimi interpolujemy GSAP-em;
   - animujemy tylko transform i opacity (autoAlpha tam, gdzie element ma stac sie niewidzialny dla dotyku i AT);
   - sticky zamiast pinu: tor .przebieg (100svh + T) i .scena sticky; wysokosc w svh, wiec pasek adresu
     nie przesuwa niczego, a ScrollTrigger.config({ ignoreMobileResize: true }) nie odswieza przy zmianie
     samej wysokosci okna;
   - ?faza=... (podglad stanow CSS): ten plik nic nie robi.

   Oś czasu (jednostki = % przewiniecia 0-100, sekcja 8 briefu; zmiany wzgledem briefu opisane w raporcie):
     0-5    przycisk znika            0-8   wieczko 0 -> 25 st. (reakcja od pierwszego piksela)
     3-12   H1 znika                  8-30  wieczko 25 -> 180 st., w ok. 90 st. (p ~ 18) przod ustepuje ramie
     3-26   kola rozstepuja sie (bliskie od 3, srednie od 4, dalekie od 5), znikaja w 16-26
     4-30   puderniczka: zawias w dol, skala 1 -> k      10-30 przyciemnienie      14-24 gorny pasek znika
     30     panel 3D ustepuje plaskiej ramie, zdjecie wchodzi w otwor lusterka
     30-48  otwarta, zdjecie powoli 1 -> 0,94 skali     48-52 zawias znika    48-58 rama znika
     48-66  podstawa zjezdza                            50-80 wzrost lusterka (zagniezdzone transformacje)
     62-84  OKLADKA: telefon - pas w kolorze przelamania wjezdza od dolu (68-84) (zaslania dol kola, wiec nie ma luku),
            desktop - panel wjezdza od lewej, H1 i pasek ustepuja; 74-84 cien pod winieta (telefon)
     72-84  winieta (nazwa) wychodzi z maski   80-88 linia wydania   77-92 pozycje spisu kolejno   86-93 CTA
     78-90  obwodka kola (tylko desktop)
     97-100 stan koncowy: okladka (zdjecie, winieta, linia, spis, CTA) */
(function () {
  'use strict';
  var d = document, root = d.documentElement;
  var G = window.gsap, ST = window.ScrollTrigger;
  var param = new URLSearchParams(location.search);

  if (param.get('faza')) return;                    /* podglad stanow CSS: nie ruszamy */
  if (!G || !ST || !d.querySelector('[data-scene="lustro"]')) { root.classList.remove('js'); return; }

  G.registerPlugin(ST);
  ST.config({ ignoreMobileResize: true });
  G.config({ force3D: true });

  var LITE = /Instagram/i.test(navigator.userAgent) || param.get('lite') === '1';   /* przegladarka w Instagramie: bez Lenis */
  var BEZ_LENIS = LITE || param.get('lenis') === '0';
  var UCHYL_KAT = 22, UCHYL_POWTORZEN = 1;          /* sekcja 7: uchylenie do 22 st., powtorka raz po 5 s bezczynnosci */
  var Q_SCENA = '(prefers-reduced-motion: no-preference) and (min-height: 501px)';
  if (LITE) root.classList.add('lite');

  var mm = null, podpis = '', postep = null;      /* postep: ostatnie 0-1 sceny, zeby przebudowa (zmiana rozmiaru) nie wyrzucala na poczatek */
  var lenisAktywny = null;                         /* Lenis sceny (desktop), uzywany tez przez kotwice spisu */

  /* ── 0 · bezpieczniki: blad = cofamy wszystko i zostaje strona statyczna ── */
  function awaria(e) {
    try { console.warn('[lustro] animacja wylaczona, zostaje wersja statyczna:', e && e.message ? e.message : e); } catch (_) {}
    setTimeout(function () {
      try { mm && mm.revert(); } catch (_) {}
      root.removeAttribute('data-animator');
      root.classList.remove('js');
    }, 0);
  }

  /* ── 1 · budowa sceny: odczyt stanow z CSS, jedna os czasu na scrubie, podpowiedz, dotyk ── */
  function zbuduj(o) {
    var scena = d.querySelector('[data-anim="scena"]');
    var tor = d.querySelector('[data-anim="przebieg"]');
    var hero = d.querySelector('[data-scene="lustro"]');
    var puder = d.querySelector('.puder');
    var a = function (n) { return scena.querySelector('[data-anim="' + n + '"]'); };
    var E = {
      dol: a('puder-dol'), gora: a('puder-gora'), panel: a('panel'), zawZ: a('zawias-z'), zawO: a('zawias-o'),
      rama: a('rama-plaska'), zdj: a('zdjecie'), wew: a('zdjecie-wew'), hi: a('lusterko-hi'), luk: a('luk'),
      pos: a('poswiata'), przy: a('przyciemnienie'), pasek: a('pasek'), h1: a('h1'), przewin: a('przewin'),
      koniec: a('koniec'), winieta: a('winieta-w'), wydanie: a('wydanie'), pas: a('pas'), cien: a('cien'), cta: a('cta-koniec'),
      slowo: a('slowo'), slowoK: a('slowo-kontur'), chwila: a('chwila'), dalej: a('dalej')
    };
    Object.keys(E).forEach(function (k) { if (!E[k]) throw new Error('brak haka ' + k); });
    if (!tor || !puder) throw new Error('brak toru sceny');
    var kola = [].slice.call(scena.querySelectorAll('[data-anim="kolo"]')).filter(function (k) { return getComputedStyle(k).display !== 'none'; });
    var strzalka = E.przewin.querySelector('svg');
    var spis = [].slice.call(scena.querySelectorAll('.spis__poz'));      /* spis tresci okladki (moze byc pusty: sam hero) */
    var sprzatanie = [];                            /* funkcje czyszczace (listenery, timery, Lenis) */
    var nasluch = function (cel, typ, fn, opcje) { cel.addEventListener(typ, fn, opcje); sprzatanie.push(function () { cel.removeEventListener(typ, fn, opcje); }); };

    if (typeof window.heroGeom === 'function') window.heroGeom();     /* --k0, --sp, --pdx, --pdy */

    /* odczyt stanow z CSS: ustaw data-faza, odczytaj, wroc (bez przejsc: html[data-podglad] nie jest ustawiany) */
    var czytaj = function (el) {
      var cs = getComputedStyle(el);
      var m = cs.transform && cs.transform !== 'none' ? new DOMMatrixReadOnly(cs.transform) : null;
      return { o: parseFloat(cs.opacity), x: m ? m.e : 0, y: m ? m.f : 0, s: m ? m.a : 1 };
    };
    var stan = { zamknieta: new Map(), otwarta: new Map(), koncowa: new Map() };
    var czytane = Object.keys(E).map(function (k) { return E[k]; }).concat(kola);
    ['zamknieta', 'otwarta', 'koncowa'].forEach(function (f) {
      if (f === 'zamknieta') scena.removeAttribute('data-faza'); else scena.setAttribute('data-faza', f);
      czytane.forEach(function (el) { stan[f].set(el, czytaj(el)); });
    });
    scena.removeAttribute('data-faza');
    var Z = function (el) { return stan.zamknieta.get(el); };
    var O = function (el) { return stan.otwarta.get(el); };
    var K = function (el) { return stan.koncowa.get(el); };
    var T = function () { return Math.round(tor.offsetHeight - scena.offsetHeight); };   /* dlugosc toru w px */
    var poprzedni = postep;                                                 /* postep sprzed przebudowy (null przy pierwszej budowie) */

    /* ── 2 · stan poczatkowy elementow, ktore w CSS czekaja w stanie zamknietym ── */
    G.set(E.zdj, { x: O(E.zdj).x, y: O(E.zdj).y, scale: O(E.zdj).s });     /* niewidoczne do p = 30, ale juz na miejscu */
    G.set(E.wew, { x: O(E.wew).x, y: O(E.wew).y, scale: O(E.wew).s });
    var spisNav = scena.querySelector('.spis');
    G.set([E.wydanie, E.cta].concat(spis), { autoAlpha: 0, y: 10 });       /* okladka: dzieci czekaja ukryte, kontener tez */
    if (spisNav) G.set(spisNav, { autoAlpha: 0 });                          /* linie spisu dopiero z pierwsza pozycja */
    G.set(E.winieta, { yPercent: 112 });                                    /* nazwa schowana pod krawedzia maski winiety */
    if (o.szeroki) G.set(E.koniec, { xPercent: -101 }); else G.set(E.pas, { yPercent: 101 });
    G.set(E.przewin, { xPercent: 0, x: 0, y: 0 });

    /* ── 3 · wieczko: dwie niezalezne skladowe kata (scrub + uchylenie), jeden zapis transformacji ── */
    var wieczko = { a: 0 }, uchyl = { a: 0 };
    var KIERUNEK = -1;      /* -1: wieczko odchyla sie od widza (jak w briefie: -22 / -25 st.), spod dolnej krawedzi wychodzi rama podstawy; +1: ku widzowi */
    var kat = function () { E.panel.style.transform = 'rotateX(' + (KIERUNEK * (wieczko.a + uchyl.a)).toFixed(3) + 'deg)'; };   /* tylko ten zapis dotyka transformacji panelu */
    sprzatanie.push(function () { E.panel.style.transform = ''; });

    /* stan wspolny dla callbackow ScrollTrigger (musi istniec przed utworzeniem osi) */
    var koniecPodp = false, podp = null, czekaj = null;
    /* will-change tylko na czas sceny. Kazdy element, ktorego krycie sie zmienia, dostaje wlasna warstwe: bez tego zmiana krycia
       przemalowuje otoczenie (pelnoekranowe przyciemnienie i poswiata = kilkanascie kafli rastra na klatke) */
    var warstwyEl = [
      [kola.concat([E.zdj, E.przewin, E.h1, E.wydanie, E.cta, E.slowo, E.slowoK], o.szeroki ? [E.koniec] : []), 'transform, opacity'],
      [[E.dol, E.gora, E.panel, E.wew, E.winieta, E.pas], 'transform'],
      [[E.przy, E.pos, E.hi, E.rama, E.luk, E.pasek, E.zawZ, E.zawO, E.cien], 'opacity']
    ];
    function warstwy(on) { warstwyEl.forEach(function (g) { g[0].forEach(function (el) { el.style.willChange = on ? g[1] : ''; }); }); }
    sprzatanie.push(function () { warstwy(false); });

    /* ── 4 · os czasu na scrubie ── */
    var szybki = 0.001;                                                     /* "natychmiastowa" zmiana na osi */
    var tl = G.timeline({
      defaults: { ease: 'none', immediateRender: false },
      scrollTrigger: {
        trigger: tor, start: 'top top', end: function () { return '+=' + T(); },
        scrub: o.lenis ? true : (o.dotyk ? true : 0.4),
        onUpdate: function (st) { postep = st.progress; if (st.progress > 0.0004) przerwijPodpowiedz(); }
      }
    });

    /* 1 · odpowiedz na pierwszy palec: przycisk, wieczko od pierwszego piksela, H1 */
    tl.fromTo(E.przewin, { autoAlpha: Z(E.przewin).o, y: 0 }, { autoAlpha: 0, y: 8, duration: 5 }, 0);
    tl.fromTo(wieczko, { a: 0 }, { a: 25, duration: 8, onUpdate: kat }, 0);
    if (O(E.h1).o < Z(E.h1).o) tl.fromTo(E.h1, { autoAlpha: Z(E.h1).o, y: 0 }, { autoAlpha: 0, y: -10, duration: 9 }, 3);
    tl.fromTo([E.slowo, E.slowoK], { autoAlpha: 1, y: 0 }, { autoAlpha: 0, y: -18, duration: 10, ease: 'power1.in' }, 2);   /* slowo ustepuje miejsca otwieranemu wieczku */

    /* 2 · rozstapienie: kola odjezdzaja promieniscie o 1,2 R + r (wektor z CSS), znikaja w 16-26 */
    kola.forEach(function (k) {
      var m = parseInt(k.getAttribute('data-miejsce').slice(1), 10);
      var start = m <= 2 ? 3 : m <= 4 ? 4 : 5;
      tl.fromTo(k, { x: 0, y: 0 }, { x: O(k).x, y: O(k).y, duration: 26 - start, ease: 'power1.in' }, start);
      tl.fromTo(k, { autoAlpha: Z(k).o }, { autoAlpha: 0, duration: 10 }, 16);
    });

    /* 3 · otwarcie: wieczko 25 -> 180, puderniczka zjezdza i rosnie, zawias zamienia sie na otwarty */
    tl.fromTo(wieczko, { a: 25 }, { a: 180, duration: 22, ease: 'power1.inOut', onUpdate: kat }, 8);
    [E.dol, E.gora].forEach(function (el) {
      tl.fromTo(el, { y: Z(el).y, scale: Z(el).s }, { y: O(el).y, scale: O(el).s, duration: 26, ease: 'power2.inOut' }, 4);
    });
    tl.fromTo(E.zawZ, { opacity: Z(E.zawZ).o }, { opacity: O(E.zawZ).o, duration: 4 }, 16);
    tl.fromTo(E.zawO, { opacity: Z(E.zawO).o }, { opacity: O(E.zawO).o, duration: 4 }, 16);
    tl.fromTo(E.przy, { opacity: Z(E.przy).o }, { opacity: O(E.przy).o, duration: 20 }, 10);
    if (O(E.pasek).o < Z(E.pasek).o) tl.fromTo(E.pasek, { autoAlpha: Z(E.pasek).o }, { autoAlpha: 0, duration: 10 }, 14);

    /* 4 · p = 30: panel 3D ustepuje plaskiej ramie, zdjecie wchodzi w otwor (ten sam kadr oka co na tylnej scianie) */
    tl.fromTo(E.panel, { autoAlpha: 1 }, { autoAlpha: 0, duration: szybki }, 30);
    tl.fromTo(E.rama, { autoAlpha: 0 }, { autoAlpha: 1, duration: szybki }, 30);
    tl.fromTo(E.zdj, { autoAlpha: 0 }, { autoAlpha: 1, duration: szybki }, 30);

    /* 5 · otwarta: zdjecie powoli 1 -> 0,94 skali, zeby odcinek nie byl martwy */
    var zoom = 0.94;
    tl.fromTo(E.wew, { scale: O(E.wew).s }, { scale: O(E.wew).s * zoom, duration: 18 }, 30);

    /* 6 · wzrost lusterka: zawias i rama znikaja, podstawa zjezdza, kolo rosnie z ciasnego kadru oka do calego posta */
    tl.fromTo(E.zawO, { opacity: O(E.zawO).o }, { opacity: K(E.zawO).o, duration: 4 }, 48);
    tl.fromTo(E.rama, { autoAlpha: 1 }, { autoAlpha: 0, duration: 10 }, 48);
    tl.fromTo(E.dol, { y: O(E.dol).y }, { y: K(E.dol).y, duration: 18, ease: 'power2.in' }, 48);
    tl.fromTo(E.zdj, { x: O(E.zdj).x, y: O(E.zdj).y, scale: O(E.zdj).s },
      { x: K(E.zdj).x, y: K(E.zdj).y, scale: K(E.zdj).s, duration: 30, ease: 'power2.inOut' }, 50);
    tl.fromTo(E.wew, { x: O(E.wew).x, y: O(E.wew).y, scale: O(E.wew).s * zoom },
      { x: K(E.wew).x, y: K(E.wew).y, scale: K(E.wew).s, duration: 30, ease: 'power2.inOut' }, 50);
    tl.fromTo(E.hi, { opacity: O(E.hi).o }, { opacity: K(E.hi).o, duration: 22 }, 52);       /* ostry kadr oka oddaje miejsce zdjeciu */
    tl.fromTo(E.pos, { opacity: Z(E.pos).o }, { opacity: K(E.pos).o, duration: 26 }, 64);
    tl.fromTo(E.przy, { opacity: O(E.przy).o }, { opacity: K(E.przy).o, duration: 26 }, 64);

    /* 7 · okladka: pas ze spisem (telefon od dolu, desktop jako panel od lewej), cien, winieta z maski, linia, spis kolejno, CTA */
    /* srodek sceny na telefonie i tablecie: zdanie u gory i podpowiedz na dole, zanim zdjecie zacznie rosnac */
    if (E.chwila && E.dalej) {
      tl.fromTo(E.chwila, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 7, ease: 'power2.out' }, 21);
      tl.fromTo(E.dalej, { autoAlpha: 0, y: 8 }, { autoAlpha: 1, y: 0, duration: 6, ease: 'power2.out' }, 25);
      tl.to([E.chwila, E.dalej], { autoAlpha: 0, y: -8, duration: 6, ease: 'power1.in' }, o.szeroki ? 50 : 56);   /* telefon: do wjazdu pasa */
    }
    tl.fromTo(E.koniec, { autoAlpha: 0 }, { autoAlpha: 1, duration: szybki }, 62);
    if (o.szeroki) {
      tl.fromTo(E.h1, { autoAlpha: 1 }, { autoAlpha: 0, duration: 6 }, 55);           /* H1 i pasek znikaja, zanim panel do nich dojedzie */
      var fakty = scena.querySelector('.fakty-hero');
      if (fakty) tl.fromTo(fakty, { autoAlpha: 1, y: 0 }, { autoAlpha: 0, y: -10, duration: 6 }, 54);
      tl.fromTo(E.pasek, { autoAlpha: 1 }, { autoAlpha: 0, duration: 6 }, 56);
      tl.fromTo(E.koniec, { xPercent: -101 }, { xPercent: 0, duration: 18, ease: 'power3.out' }, 62);
      tl.fromTo(E.luk, { opacity: Z(E.luk).o }, { opacity: K(E.luk).o, duration: 12 }, 78);
    } else {
      /* telefon: pas wjezdza zaraz za rosnacym zdjeciem (58), z trescia od razu - wczesniej przy 60-75 % dol ekranu stal pusty */
      tl.fromTo(E.pas, { yPercent: 101 }, { yPercent: 0, duration: 14, ease: 'power3.out' }, 58);
      tl.fromTo(E.cien, { opacity: 0 }, { opacity: K(E.cien).o, duration: 10 }, 64);
    }
    var t0 = o.szeroki ? 0 : -10;                                         /* telefon: okladka 10 jednostek wczesniej, razem z pasem */
    tl.fromTo(E.winieta, { yPercent: 112 }, { yPercent: 0, duration: 12, ease: 'power3.out' }, 72 + t0);
    tl.fromTo(E.wydanie, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 8, ease: 'power2.out' }, 80 + t0);
    if (spisNav) tl.fromTo(spisNav, { autoAlpha: 0 }, { autoAlpha: 1, duration: 4 }, 76 + t0);
    var krok = spis.length ? Math.min(1.6, 9 / spis.length) : 0;
    spis.forEach(function (el, i) {
      tl.fromTo(el, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 6, ease: 'power2.out' }, 77 + t0 + i * krok);
    });
    tl.fromTo(E.cta, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 7, ease: 'power2.out' }, 86 + t0);
    tl.set({}, {}, 100);                                                    /* os ma dokladnie 100 jednostek */
    if (o.szeroki && spis.length && E.pasek && !E.pasek.querySelector('.pasek__menu')) {
      var menu = document.createElement('div');
      menu.className = 'pasek__menu';
      spis.slice(0, 5).forEach(function (a) {
        var l = document.createElement('a'), t = a.querySelector('.spis__tyt');
        l.href = a.getAttribute('href'); l.textContent = (t || a).textContent;
        menu.appendChild(l);
      });
      E.pasek.insertBefore(menu, E.pasek.lastElementChild);
      sprzatanie.push(function () { if (menu.parentNode) menu.parentNode.removeChild(menu); });
    }
    var st = tl.scrollTrigger;
    /* jednorazowy przebieg osi na budowie: GSAP inicjuje wszystkie tweeny (odczyty stylow) teraz, a nie w trakcie pierwszego przewijania */
    tl.progress(1, true).progress(0, true);
    st.update(true);
    kat();                                                                  /* callbacki sa tlumione przy przebiegu, wiec kat wieczka ustawiamy sami */

    /* will-change trzymamy, dopoki hero jest w ogole widoczne (dluzej niz sam tor: zdjecie odjezdza razem ze sticky), a zdejmujemy poza ekranem */
    ST.create({ trigger: hero, start: 'top bottom', end: 'bottom top', onToggle: function (t) { warstwy(t.isActive); } });
    warstwy(true);

    /* ── 5 · podpowiedz: wieczko samo sie uchyla po 1,6 s, raz, powtorka raz po 5 s bezczynnosci ── */
    function uchylenie(n) {
      czekaj = null;
      if (koniecPodp || tl.progress() > 0.001 || window.scrollY > 2) return;
      podp = G.timeline({ onComplete: function () { podp = null; if (n < UCHYL_POWTORZEN) czekaj = G.delayedCall(5, function () { uchylenie(n + 1); }); } });
      podp.to(uchyl, { a: UCHYL_KAT, duration: 0.55, ease: 'power2.out', onUpdate: kat })
        .to(uchyl, { a: 0, duration: 0.9, ease: 'power2.inOut', onUpdate: kat });
      if (n > 0 && strzalka) podp.fromTo(strzalka, { y: 0 }, { y: 5, duration: 0.45, ease: 'sine.inOut', yoyo: true, repeat: 1, clearProps: 'transform' }, 0);
    }
    function przerwijPodpowiedz() {
      if (koniecPodp) return;
      koniecPodp = true;
      if (czekaj) { czekaj.kill(); czekaj = null; }
      if (podp) { podp.kill(); podp = null; }
      if (uchyl.a !== 0) G.to(uchyl, { a: 0, duration: 0.22, ease: 'power2.out', overwrite: true, onUpdate: kat });
    }
    var KLAWISZE = { ArrowDown: 1, ArrowUp: 1, PageDown: 1, PageUp: 1, ' ': 1, Home: 1, End: 1 };
    nasluch(window, 'scroll', function () { if (window.scrollY > 1) przerwijPodpowiedz(); }, { passive: true });
    nasluch(window, 'wheel', przerwijPodpowiedz, { passive: true });
    nasluch(window, 'touchstart', przerwijPodpowiedz, { passive: true });
    nasluch(window, 'pointerdown', przerwijPodpowiedz, { passive: true });
    nasluch(window, 'keydown', function (e) { if (KLAWISZE[e.key]) przerwijPodpowiedz(); });
    sprzatanie.push(function () { if (czekaj) czekaj.kill(); if (podp) podp.kill(); });
    var wieczkoImg = E.panel.querySelector('img');
    var pierwszeMalowanie = [d.fonts && d.fonts.ready, wieczkoImg && wieczkoImg.decode ? wieczkoImg.decode().catch(function () {}) : null];
    Promise.all(pierwszeMalowanie).then(function () {
      requestAnimationFrame(function () { if (!koniecPodp) czekaj = G.delayedCall(1.6, function () { uchylenie(0); }); });
    });

    /* ── 6 · dotkniecie: puderniczka i przycisk przewijaja po tej samej osi (0 -> 40 %, pauza 0,6 s, 40 -> 100 %) ── */
    var auto = null, ostatnie = 0;
    var ustawScroll = o.lenis ? function (y) { o.lenis.scrollTo(y, { immediate: true, force: true }); } : function (y) { window.scrollTo(0, y); };
    function przerwijAuto() { if (auto) { auto.kill(); koniecAuto(); } }
    function koniecAuto() {
      auto = null;
      ['wheel', 'touchstart', 'mousedown', 'keydown'].forEach(function (t) { window.removeEventListener(t, przerwijAuto, true); });
    }
    function przewijaj(zKlawiatury) {
      if (auto) return;
      przerwijPodpowiedz();
      var p0 = st.start, p1 = st.end, dl = p1 - p0, y0 = window.scrollY;
      if (y0 >= p1 - 2) return;
      var y40 = p0 + 0.4 * dl, ruch = { y: y0 };
      var pisz = function () {
        if (Math.abs(window.scrollY - ostatnie) > 3 && ostatnie) { przerwijAuto(); return; }      /* ktos przejal przewijanie */
        ostatnie = ruch.y; ustawScroll(ruch.y);
      };
      ostatnie = 0;
      var seq = G.timeline({ onComplete: function () { koniecAuto(); if (zKlawiatury && E.cta) E.cta.focus({ preventScroll: true }); } });
      var od = y0;
      if (y0 < y40 - 1) {
        seq.to(ruch, { y: y40, duration: Math.max(0.5, 1.2 * (y40 - y0) / (0.4 * dl)), ease: 'power2.inOut', onUpdate: pisz });
        seq.to({}, { duration: 0.6 });
        od = y40;
      }
      seq.to(ruch, { y: p1, duration: Math.max(0.5, 1.2 * (p1 - od) / (0.6 * dl)), ease: 'power2.inOut', onUpdate: pisz });
      auto = seq;
      ['wheel', 'touchstart', 'mousedown', 'keydown'].forEach(function (t) { window.addEventListener(t, przerwijAuto, { capture: true, passive: true }); });
    }
    sprzatanie.push(function () { if (auto) auto.kill(); koniecAuto(); });
    nasluch(E.przewin, 'click', function (e) { e.preventDefault(); przewijaj(e.detail === 0); });
    nasluch(puder, 'click', function () { if (tl.progress() < 0.3) przewijaj(false); });

    /* link "Przejdz do tresci" w stanie sceny prowadzi za hero (sama scena nie jest trescia do pominiecia) */
    var pomin = d.querySelector('.pomin'), pominHref = pomin && pomin.getAttribute('href');
    if (pomin && d.getElementById('uslugi')) { pomin.setAttribute('href', '#uslugi'); sprzatanie.push(function () { pomin.setAttribute('href', pominHref); }); }

    /* ── 7 · obrazy sceny: lazy -> eager i dekodowanie zaraz po pierwszym malowaniu (paczka 2), zeby nic nie doszlo w trakcie scrubu ── */
    var obrazy = [].slice.call(scena.querySelectorAll('img')).filter(function (im) { return im.loading === 'lazy' || !im.complete; });
    var ladujObrazy = function () { obrazy.forEach(function (im) { im.loading = 'eager'; if (im.decode) im.decode().catch(function () {}); }); };
    if (d.readyState === 'complete') ladujObrazy(); else nasluch(window, 'load', ladujObrazy);

    /* ── 8 · Lenis na desktopie (kolko myszy), ticker GSAP jako jedyne zrodlo klatek ── */
    if (o.lenis) {
      var tick = function (t) { o.lenis.raf(t * 1000); };
      o.lenis.on('scroll', ST.update);
      G.ticker.add(tick);
      G.ticker.lagSmoothing(0);
      lenisAktywny = o.lenis;
      sprzatanie.push(function () { G.ticker.remove(tick); G.ticker.lagSmoothing(500, 33); lenisAktywny = null; o.lenis.destroy(); });
    }

    /* po przebudowie (zmiana rozmiaru) ScrollTrigger potrafi cofnac przewiniecie do 0, a tor zmienia dlugosc: wracamy na ten sam postep sceny */
    if (poprzedni > 0.001) {
      var wroc = function () {
        var y = st.start + poprzedni * (st.end - st.start);
        if (o.lenis) o.lenis.scrollTo(y, { immediate: true, force: true }); else window.scrollTo(0, y);
      };
      requestAnimationFrame(wroc); setTimeout(wroc, 150);
    }
    podpis = window.innerWidth + 'x' + scena.offsetHeight;
    root.setAttribute('data-animator', 'gsap');
    return function () {
      sprzatanie.forEach(function (f) { try { f(); } catch (_) {} });
      root.removeAttribute('data-animator');
    };
  }

  /* ── 9 · matchMedia: tryb sceny / statyczny, desktop (Lenis) vs dotyk; przy zmianie wszystko od nowa ── */
  function inicjuj() {
    mm = G.matchMedia();
    mm.add({ scena: Q_SCENA, szeroki: '(min-width: 1100px)', mysz: '(hover: hover) and (pointer: fine)', zawsze: 'all' }, function (ctx) {   /* 'zawsze': bez niego telefon w trybie statycznym nie uruchamialby funkcji */
      var c = ctx.conditions;
      if (!c.scena) { postep = null; root.classList.remove('js'); return; }
      root.classList.add('js');
      try {
        var lenis = null;
        if (c.szeroki && c.mysz && !BEZ_LENIS && window.Lenis) {
          lenis = new window.Lenis({ lerp: 0.16, smoothWheel: true, syncTouch: false, autoRaf: false });
        }
        return zbuduj({ szeroki: c.szeroki, lenis: lenis, dotyk: !c.mysz });
      } catch (e) { awaria(e); }
    });
  }

  function odswiez() {
    try { if (G.matchMediaRefresh) G.matchMediaRefresh(); else { mm.revert(); inicjuj(); } } catch (e) { awaria(e); }
  }
  var opoznienie = 0;
  addEventListener('resize', function () {
    clearTimeout(opoznienie);
    opoznienie = setTimeout(function () {
      /* zmiana samej wysokosci okna z powodu paska adresu: scena ma wysokosc w svh, wiec podpis sie nie zmienia i nie budujemy od nowa */
      var s = d.querySelector('[data-anim="scena"]');
      if (s && root.hasAttribute('data-animator') && (window.innerWidth + 'x' + s.offsetHeight) !== podpis) odswiez();
    }, 220);
  });

  /* ── 10a · spis: dlugi @nick lamie sie po kropce i podkresleniu, a nie w srodku slowa (gdy generator nie wstawil <wbr>) ── */
  [].forEach.call(d.querySelectorAll('#hero .spis__tyt'), function (el) {
    if (el.children.length || !/@\S{12,}/.test(el.textContent)) return;
    el.innerHTML = el.textContent.replace(/[&<>]/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]; }).replace(/([._])(?=\S)/g, '$1<wbr>');
  });

  try { inicjuj(); } catch (e) { awaria(e); }

  /* ── 10 · spis tresci okladki: kotwice do sekcji (Lenis na desktopie, plynnie natywnie gdzie indziej, skok przy ograniczonym
     ruchu), fokus na celu. sekcje.js pomija linki z #hero, wiec obsluga jest tylko tutaj ── */
  d.addEventListener('click', function (e) {
    var a = e.target.closest && e.target.closest('#hero .spis a[href^="#"], #hero .pasek__menu a[href^="#"]');
    if (!a || e.defaultPrevented || e.button || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    var cel = null;
    try { cel = d.getElementById(decodeURIComponent(a.getAttribute('href').slice(1))); } catch (_) {}
    if (!cel) return;
    e.preventDefault();
    var spokoj = matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (lenisAktywny) lenisAktywny.scrollTo(cel, { duration: 1.2, immediate: spokoj, force: true });
    else window.scrollTo({ top: cel.getBoundingClientRect().top + window.scrollY, behavior: spokoj ? 'auto' : 'smooth' });
    if (!cel.matches('a,button,input,select,textarea,summary,[tabindex]')) cel.setAttribute('tabindex', '-1');
    cel.focus({ preventScroll: true });
    if (cel.id && location.hash !== '#' + cel.id) history.pushState(null, '', '#' + cel.id);
  });

  /* odswiezenie po kroju i po zaladowaniu (polozenie toru sie nie zmienia, ale tekst pod nim tak) */
  addEventListener('load', function () { if (root.hasAttribute('data-animator')) ST.refresh(); });
  if (d.fonts && d.fonts.ready) d.fonts.ready.then(function () { if (root.hasAttribute('data-animator')) ST.refresh(); });
})();
