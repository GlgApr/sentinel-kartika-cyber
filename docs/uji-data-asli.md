# Uji pada Data Asli — SENTINEL

Data sintetis selalu terlihat bagus di atas kertas. Dokumen ini mencatat apa yang terjadi saat SENTINEL
diuji pada **data media sosial asli**, termasuk kegagalannya, dan bagaimana setiap perbaikan diuji ulang
pada data segar yang belum pernah dilihat.

Tanggal uji: 11 November 2026. Data mentah **tidak disimpan di repo** (data pribadi pihak ketiga); dokumen
ini hanya memuat angka agregat, kode merek judi, dan contoh templat teks.

## 1. Data

Komentar publik TikTok Indonesia ditarik lewat ScrapeCreators (`/v1/tiktok/video/comments`, timestamp
detik asli). Komentar dipilih karena di situlah spam judi online (judol) dan buzzer bekerja; hasil
pencarian video biasa tidak menunjukkan koordinasi.

| Set | Peran | Topik pencarian | Video | Komentar |
|---|---|---|---|---|
| 1 | Tuning (dilihat saat memperbaiki) | TNI AD, rekrutmen TNI, judi online, demo DPR | 16 | 1.122 |
| 2–4 | Held-out v2, lalu dipakai analisis kegagalan | prabowo, kabur aja dulu, berita viral, bandar judi, slot gacor, timnas, lowongan, giveaway, togel, live slot, DPR, rupiah | 49 | 4.734 |
| 5–6 | **Held-out final** (kode dibekukan, hash dicatat sebelum data ditarik) | polisi viral, harga beras, gaji TNI, slot online, korupsi, jedag jedug, edit video, mahjong ways, pola gacor, sound viral | 30 | 2.002 |

**Label.** Akun spam promosi (judol) ditandai bila komentarnya mendorong kode merek/mention yang dipakai
≥ 2 akun berbeda, lalu **setiap akun diperiksa manual**. Akun yang di-flag SENTINEL tetapi tidak berlabel
juga diperiksa satu per satu; yang terbukti spam ditambahkan ke label (semuanya spam: lihat §4).
Keterbatasan: spam yang lolos dari heuristik label **dan** dari SENTINEL tidak terhitung, sehingga
recall bisa sedikit lebih rendah dari angka di bawah. Komentar politik (slogan, seruan) tidak diberi label
"buzzer" karena kebenarannya tidak bisa diverifikasi dari luar.

## 2. Hasil akhir (held-out final, set 5–6)

| Metode | Precision | Recall | F1 | Tuduhan salah |
|---|---|---|---|---|
| **SENTINEL** | **100 %** | **88 %** | **94 %** | **0** |
| Baseline A — burst monitor | 4 % | 99 % | 8 % | 1.617 akun |
| Baseline B — duplicate filter | 13 % | 28 % | 18 % | 124 akun |

2.002 komentar, 69 akun spam berlabel. Set 5 (topik berita/politik) tidak berisi spam promosi dan SENTINEL
tidak mem-flag apa pun. Set 6 berisi 6 operasi judol berbeda (mis. kode MATA13, FALCON, Macanplay, ZOYA55,
VIKING27, GIOK168) dan semuanya tertangkap.

Seluruh set (8.000+ komentar, 6 set): **0 akun organik dituduh**. Slogan politik yang diulang banyak akun
("nkri harga mati" 7 akun, "tangkap ..." 6 akun) **tidak** di-flag karena tidak ada bukti koordinasi;
filter duplikat menuduh semuanya.

## 3. Perjalanan: dari 0 tertangkap ke F1 94 %

| Iterasi | Yang ditemukan di data asli | Perbaikan | Diuji pada |
|---|---|---|---|
| v1 (versi lomba awal) | **0 campaign** pada set 1, padahal ada jaringan spam judol Thai (`@MMM5 คืออะไรหรอ`). Normalisasi teks membuang huruf non-Latin, emoji, dan huruf "fancy" unicode (`𝐆𝐀𝐌𝐄𝟏𝟗𝟏`) | Normalisasi NFKC + pertahankan semua aksara; mention dan kode merek (`xv99`) dihitung sebagai target promosi | set 1 |
| | Syarat "pasangan akun yang sama beraksi ≥ 2 kali" terlalu ketat: tiap akun spam muncul 1–2 kali, yang berulang adalah **kelompoknya** | Pengulangan **level motif**: templat + target yang sama muncul di ≥ 2 gelombang terpisah. Hanya untuk target kuat (mention/kode/URL), bukan tagar topik | set 1 + benchmark sintetis |
| | Sinyal profil akun = 0 karena komentar tidak membawa data profil; "tidak tahu" dihitung "normal" | Bobot dinormalisasi ulang bila data profil tidak ada | set 1 |
| v2 | Held-out: operasi `Hera56 / VlKlNG27 / Ljrjk789` ditemukan tapi skornya 0,543 (lolos). Amplifikasi hanya menghitung satu target teratas | Amplifikasi = porsi post yang mendorong target promosi apa pun | set 2–4 |
| | Kata ulang Indonesia (`laki2`, `orang2`) terbaca sebagai kode merek | Pengecualian kata ulang dan satuan (`5kg`, `80rb`) | set 2–4 |
| | Homoglyph: `𝐕𝐈𝐊𝐈𝐍𝐆➋➐` dan `VlKlNG27` tidak dikenali sebagai merek yang sama | Angka dekoratif → angka biasa; kunci skeleton l→i | set 2–4 |
| | **Recall 0 %** pada video "live slot" berisi ±35 akun: pola **tetes lambat**, berhari-hari, tanpa keserempakan | Detektor **operasi templat**: graf bipartit templat ↔ target; syarat rotasi (satu templat untuk ≥ 2 merek / satu merek lewat ≥ 2 templat) | set 4 |
| v3 (final, dibekukan) | — | — | **set 5–6: P 100 %, R 88 %** |

Benchmark sintetis tidak turun selama perbaikan (precision tetap 100 %; F1 pada penyamaran tertinggi
naik dari 68 % ke 94,6 %), jadi data sintetis tetap dipakai sebagai pagar regresi.

## 4. Pola operasi yang ditemukan di data asli

1. **Gelombang serentak berbahasa Thai**: 3–5 akun dalam ≤ 10 menit memposting `@<KODE> คืออะไรหรอ`
   ("<KODE> itu apa?") dengan emoji berbeda; kode berganti tiap gelombang (XV99, MMM5, 8DDD).
2. **Pujian palsu + mention merek**: `@VlKlNG27_ 💜 suka banget sama editingnya!` dari akun bernama
   Indonesia wajar (sockpuppet), 4–7 akun per gelombang, berulang di hari berbeda.
3. **Tetes lambat**: templat tetap (`MAIN SANTAI AJA BG, YANG PENTING ADA SENSASI PECAH...`,
   `TIPIS TIPIS AJA`, `Sangat menakjubkan sekali ketua`) dipakai puluhan akun selama berminggu-minggu sambil
   memutar 10–15 kode merek. Tidak ada keserempakan waktu sama sekali.
4. **Trik penghindar filter**: huruf matematis unicode, angka dalam lingkaran (➊➏➑), homoglyph (l untuk I),
   huruf dieja terpisah (`u b e t 9 6`).

Semua 44 akun yang di-flag SENTINEL di luar label awal ternyata spam setelah diperiksa manual
(kode merek mereka hanya dipakai satu akun, tetapi templatnya sama dengan operasi).

## 5. Yang belum bisa (diungkap jujur)

- **Spam satu merek, satu templat** (mis. 4 akun `BUNGA32 tipis tipis aja`): secara struktur sama dengan
  kutipan/meme organik, jadi sengaja tidak di-flag tanpa sinyal lain. Bisa ditangkap bila profil akun
  ditarik (umur, nama generik) — 1 kredit per akun.
- **Spam solo** (satu akun memposting berkali-kali sendirian) bukan koordinasi; masuk lensa per akun.
- **Buzzer politik**: tidak ada label kebenaran di data publik, sehingga akurasinya belum bisa diukur.
  Yang bisa ditunjukkan: SENTINEL tidak menuduh slogan organik.

## 6. Lensa buzzer per akun: tidak lolos uji data asli

Lensa per akun diuji pada **Cresci-2017** (dataset bot Twitter berlabel, WWW '17), 300 akun per kelompok,
hanya akun dengan ≥ 5 tweet:

| Kelompok | Skor ≥ 25 | AUC vs akun asli |
|---|---|---|
| Akun asli (genuine) | 26,7 % (alarm palsu) | — |
| Traditional spambots #1 | 15,3 % | 0,32 |
| Social spambots #1 (retweet politik) | 1,3 % | 0,37 |
| Social spambots #2 | 14,7 % | 0,55 |
| Social spambots #3 (spam produk) | 8,3 % | 0,41 |

AUC ≤ 0,55 berarti **tidak lebih baik dari acak**: akun manusia yang sangat aktif mendapat skor lebih
tinggi daripada bot. Angka F1 93,6 % pada data sintetis **tidak berlaku** di data asli dan tidak kami klaim.
Hasil ini sejalan dengan temuan utama paper Cresci sendiri: bot sosial modern tidak bisa dibedakan per
akun, hanya di level kelompok. Karena itu halaman *Profil akun* kini diposisikan sebagai lembar konteks
untuk analis, dan bukti yang dianggap valid adalah keanggotaan akun dalam operasi terkoordinasi.

### Lensa jaringan pada Cresci-2017

150 bot + 150 akun asli per uji, 60 tweet per akun (versi final v3, tanpa penyetelan pada Cresci):

| Kelompok bot | SENTINEL | Duplicate filter |
|---|---|---|
| Social spambots #1 (retweet kandidat politik) | P 88 %, R 29 %, F1 43 %; 6 akun asli dituduh | P 75 %, R 99 %, F1 85 %; **49 dari 150 akun asli dituduh** |
| Social spambots #3 (promosi produk) | 0 bot tertangkap; **6 akun asli dituduh** | P 74 %, R 92 %, F1 82 %; 49 akun asli dituduh |

Dua kelemahan nyata yang terlihat di sini:

1. **Bot berbagi-ulang tanpa keserempakan** (me-retweet konten yang sama tersebar berhari-hari) belum
   ditangani. Pola baku di riset untuk ini adalah jaringan *co-share* lintas banyak konten berbeda
   (Pacheco dkk., ICWSM 2021); masuk rencana pengembangan.
2. **Alarm palsu: kerumunan yang menjawab satu akun pemancing.** Enam akun asli Cresci adalah peserta
   proyek riset gempa yang dipancing bersamaan oleh akun riset ("apakah Anda merasakan gempa?") dan
   membalas di menit yang sama, berulang di beberapa gempa. Skornya 0,557, tepat di atas ambang. Inilah
   alasan setiap flag tetap melalui keputusan analis (*human-in-the-loop*).

Catatan konteks: Cresci adalah Twitter 2014–2015 berbahasa Inggris/Italia; target SENTINEL adalah
TikTok/medsos Indonesia 2026. Hasil di §2 lebih relevan untuk penggunaan TNI AD, tetapi hasil Cresci
menunjukkan batas metode secara jujur.

## 7. Reproduksi

Skrip uji ada di luar repo (memuat data pribadi). Alurnya: tarik komentar per video
(`ScrapeCreators._call("/v1/tiktok/video/comments", url=...)`), ubah ke format post SENTINEL
(`account_id`, `content`, `timestamp` dari `create_time`), jalankan `DetectionEngine.detect`, lalu
bandingkan dengan `baseline_burst` dan `baseline_duplicate` dari `src/evaluation.py`. Uji regresi untuk
setiap pola nyata ada di `tests/test_pipeline.py` (spam Thai lintas gelombang, tetes lambat, homoglyph,
kata ulang).
