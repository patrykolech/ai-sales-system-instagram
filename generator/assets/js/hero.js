/* hero.js: pomocnik geometrii sceny hero. To NIE jest animacja (animacje: main.js, GSAP).
   1) Liczy cztery liczby, ktorych CSS nie policzy (dzielenie dlugosci przez dlugosc):
      --k0  skala kontenera zdjecia w fazie otwartej,
      --sp  skala zdjecia wewnatrz kontenera,
      --pdx, --pdy  przesuniecie zdjecia (srodek kadru oka -> srodek kontenera).
      main.js wola window.heroGeom() przed kazda budowa sceny.
   2) ?faza=zamknieta|otwarta|koncowa wymusza stan CSS (do przegladu i zrzutow, bez animatora;
      main.js przy tym parametrze nic nie robi).
   Wersja z etapu 2 przelaczala fazy wg przewiniecia i dawala przejscia CSS (html[data-podglad]).
   To zostalo usuniete w etapie 3: animator przejmuje scene, wiec nic tu nie ustawia data-faza ani
   data-podglad (css nadal zna te selektory, bo sluza do odczytu stanow koncowych i do ?faza).
   Dziala tylko w stanie sceny (position: sticky na .scena); poza nim nic nie robi. */
/* 3) Przegladarka w Instagramie / Facebooku (WebView): jej paski chowaja sie przy przewijaniu, a svh/lvh ida za tym
   (w Safari svh stoi). CSS przeliczal wtedy rame i kola, a os GSAP zostawala na starych pikselach: zdjecie oka wyjezdzalo
   z ramy, napis wchodzil na pasek (zrzut wlasciciela z iPhone'a, 2026-11-15). Tam zamrazamy --vh1 i --ekran-duzy w px;
   nowy pomiar tylko przy zmianie szerokosci (obrot) albo przed pierwszym przewinieciem (WebView potrafi podac zla
   wysokosc przy starcie) - wtedy sztuczny resize, zeby main.js przebudowal scene. */
(function () {
  'use strict';
  if (!/Instagram|FBAN|FBAV|FB_IAB/i.test(navigator.userAgent) && new URLSearchParams(location.search).get('iab') !== '1') return;
  var r = document.documentElement, szer = 0, wys = 0;
  function duzy() {
    var p = document.createElement('div');
    p.style.cssText = 'position:absolute;left:-9px;top:0;width:1px;height:100vh;visibility:hidden;pointer-events:none';
    if (window.CSS && CSS.supports && CSS.supports('height', '100lvh')) p.style.height = '100lvh';
    (document.body || r).appendChild(p);
    var h = p.offsetHeight;
    p.parentNode.removeChild(p);
    return h;
  }
  function zmierz(wymus) {
    var w = window.innerWidth, h = window.innerHeight;
    if (!h || !w) return false;
    if (!wymus && w === szer) return false;
    if (w === szer && h === wys) return false;
    szer = w; wys = h;
    r.style.setProperty('--vh1', (h / 100).toFixed(3) + 'px');
    r.style.setProperty('--ekran-duzy', Math.max(h, duzy()) + 'px');
    return true;
  }
  zmierz(true);
  addEventListener('resize', function () { zmierz(false); });
  function ponow() {
    if ((window.scrollY || 0) < 5 && zmierz(true)) dispatchEvent(new Event('resize'));
  }
  addEventListener('load', ponow);
  setTimeout(ponow, 600);
  setTimeout(ponow, 1500);
})();

(function () {
  'use strict';
  var d = document;
  var hero = d.querySelector('[data-scene="lustro"]');
  var scena = d.querySelector('[data-anim="scena"]');
  if (!hero || !scena) return;
  var O = scena.querySelector('[data-anim="zdjecie"]');
  var P = scena.querySelector('[data-anim="zdjecie-wew"]');
  var baza = scena.querySelector('[data-anim="podstawa"]');
  var wymuszona = new URLSearchParams(location.search).get('faza');

  function aktywna() { return getComputedStyle(scena).position === 'sticky'; }
  function liczba(el, nazwa) { return parseFloat(getComputedStyle(el).getPropertyValue(nazwa)); }

  function geom() {
    if (!aktywna() || !O || !P || !baza) return;
    var k = liczba(hero, '--k') || 1.111;
    var R0 = (baza.offsetWidth / 2) * k;
    var rh = 0.8805 * R0;               /* promien otworu lustra (baza/uklad.json) */
    var rF = O.offsetWidth / 2;         /* promien koncowego kola zdjecia */
    var c = (liczba(P, '--kx1') - liczba(P, '--kx0')) * P.offsetWidth;   /* bok kadru oka w px ukladu */
    var qx = P.offsetLeft + liczba(P, '--cx0') * P.offsetWidth;
    var qy = P.offsetTop + liczba(P, '--cy0') * P.offsetHeight;
    scena.style.setProperty('--k0', (rh / rF).toFixed(4));
    scena.style.setProperty('--sp', (2 * rF / c).toFixed(4));
    scena.style.setProperty('--pdx', (rF - qx).toFixed(2) + 'px');
    scena.style.setProperty('--pdy', (rF - qy).toFixed(2) + 'px');
  }

  function start() {
    geom();
    if (wymuszona === 'otwarta' || wymuszona === 'koncowa') scena.setAttribute('data-faza', wymuszona);
  }
  addEventListener('resize', geom);
  addEventListener('orientationchange', geom);
  if (d.readyState === 'loading') d.addEventListener('DOMContentLoaded', start); else start();
  window.heroGeom = geom;
})();
