# Naskah Video SENTINEL (target 8:30, batas 10:00)

Rekam layar 1920×1080 dari demo online atau `./run.sh`. Sebelum merekam:
- buka **Sumber data → Skenario demo** lalu muat ulang, supaya antrean berisi 3 kasus;
- pastikan **Mode Presentasi** aktif (username disamarkan);
- tutup tab lain dan notifikasi.

Narasi ditulis untuk dibaca santai (±130 kata per menit). Bagian dalam [kurung siku] adalah aksi di layar.

---

## 0:00–0:40 · Pembuka (slide 1–2)

[Slide 1: judul SENTINEL]

> Bayangkan ada tagar yang tiba-tiba trending, atau hoaks rekrutmen "jalur khusus" yang mencatut nama TNI AD.
> Pertanyaan pertama analis selalu sama: ini suara publik yang asli, atau puluhan akun yang digerakkan satu operator?

[Slide 2: masalah]

> Dashboard monitoring biasa tidak bisa menjawabnya, karena hanya menghitung volume. Berita gempa dan kampanye buzzer
> sama-sama menghasilkan lonjakan. Operator juga sengaja menghindari filter dengan huruf unicode, angka dekoratif,
> dan ejaan yang diacak. Kami membangun SENTINEL untuk menjawab pertanyaan itu, dengan bukti.

## 0:40–1:20 · Ide inti (slide 3)

> SENTINEL tidak menilai isi opini. SENTINEL menilai cara akun bertindak bersama. Ada tiga tanda: serentak, berulang,
> dan seragam. Ribuan orang bisa membahas gempa di jam yang sama, tetapi tidak dengan kelompok akun yang sama, berulang
> kali, memakai templat yang sama. Karena berbasis perilaku, SENTINEL tidak butuh data latih dan netral terhadap opini
> politik.

## 1:20–2:30 · Demo: Ancaman

[Buka halaman Ancaman]

> Ini halaman pertama yang dilihat analis. Di atas ada status siaga dan empat angka kunci: 1.679 post, 198 akun,
> 3 operasi aktif, 38 akun terlibat.

[Arahkan kursor ke grafik aktivitas per jam]

> Batang merah adalah post dari jaringan terkoordinasi. Perhatikan lonjakan abu-abu tertinggi ini: itu berita gempa,
> percakapan organik. SENTINEL sengaja tidak menandainya karena tidak ada koordinasi berulang. Alat berbasis volume
> akan menjadikannya alarm.

[Arahkan ke antrean kasus]

> Di bawah ada antrean kasus, diurutkan dari yang paling berisiko. Saya buka yang teratas.

[Klik baris CMP pertama]

## 2:30–4:00 · Demo: Berkas kasus

> Ini berkas kasusnya: 18 akun mendorong satu tagar dalam 12 gelombang.

[Arahkan ke barcode sinkronisasi]

> Grafik ini kami sebut barcode sinkronisasi. Setiap garis adalah satu post. Garis yang berbaris vertikal berarti akun
> yang berbeda memposting di menit yang sama, dan pola itu berulang sepanjang hari. Ini sulit dibantah.

[Arahkan ke panel "Kenapa ditandai"]

> Skornya 0,86, dan kami tunjukkan dari mana angka itu datang: sinkronisasi waktu, keseragaman narasi, anomali profil,
> kepadatan jaringan, dan amplifikasi. Di bawahnya ada temuan tertulis dalam Bahasa Indonesia.

[Tab Bukti → scroll tabel → tunjuk tombol unduh dan hash]

> Tab Bukti berisi semua post. Bukti bisa diunduh dengan sidik jari SHA-256, sehingga bisa dibuktikan tidak berubah
> sejak diunduh.

[Tab Jaringan]

> Tab Jaringan menunjukkan siapa penggerak dan siapa penguat.

[Tab Tindakan dan laporan → pilih keputusan → tunjuk riwayat audit & tombol unduh Markdown / STIX 2.1]

> Terakhir, analis yang memutuskan: tinjau, eskalasi, atau abaikan—setiap keputusan tercatat di riwayat audit.
> Laporan intelijen siap kirim dibuat otomatis dalam format Markdown maupun standar STIX 2.1 JSON untuk integrasi SOC.
> SENTINEL memberi rekomendasi, manusia yang memutuskan.

## 4:00–4:40 · Demo: Sumber data dan Profil akun (singkat)

[Buka Sumber data → tunjuk Data live, Unggah file]

> Data bisa ditarik live dari TikTok, YouTube, X, Threads, Instagram, dan Mastodon, atau diunggah sebagai CSV untuk
> jaringan tertutup satuan.

[Buka Profil akun → pilih satu akun]

> Halaman Profil akun memberi konteks per akun. Kami tandai jelas bahwa ini indikator, bukan vonis. Alasannya ada di
> bagian berikut.

## 4:40–6:50 · Uji pada data asli (slide 7–9)

[Slide 7]

> Data sintetis selalu terlihat bagus. Jadi kami menguji SENTINEL di data asli: sekitar 8.000 komentar TikTok Indonesia
> dari 95 video, dengan akun spam judi online diperiksa satu per satu.
> Hasil pertama: nol. SENTINEL tidak menangkap satu pun. Normalisasi teks membuang huruf Thai dan huruf unicode
> "fancy", dan yang berulang ternyata kelompoknya, bukan pasangan akunnya.
> Kami memperbaikinya, lalu menguji di data baru, dan menemukan kelemahan lain: homoglyph seperti l untuk I, kata ulang
> "laki2" yang dikira kode merek, dan spam "tetes lambat" yang tersebar berhari-hari tanpa posting serentak.

> Untuk uji akhir, kode kami bekukan dan hash-nya dicatat sebelum data baru ditarik, jadi tidak ada penyetelan pada data
> uji.

[Slide 8]

> Hasilnya: F1 94 persen dengan precision 100 persen. Nol akun yang dituduh salah. Filter teks kembar hanya 18 persen dan
> menuduh 124 akun tidak bersalah. Pemantau lonjakan 8 persen dan menuduh lebih dari 1.600 akun. Slogan politik yang
> diulang banyak akun tidak ditandai, karena tidak ada bukti koordinasi.

[Slide 9]

> Dari data ini kami menemukan tiga pola operasi nyata: gelombang serentak, motif pujian palsu yang berulang, dan operasi
> templat tetes lambat. Ketiganya kini menjadi tes otomatis.

## 6:50–7:40 · Yang belum bisa (slide 10)

> Kami juga ingin jujur soal batasnya. Kami menguji skor per akun di dataset bot berlabel Cresci-2017, dan hasilnya
> setara tebakan acak. Karena itu Profil akun kami posisikan sebagai lembar konteks, dan bukti yang kami anggap sah
> adalah keanggotaan dalam operasi terkoordinasi. Bot retweet yang tidak serentak baru tertangkap 29 persen, dan ada
> satu mode alarm palsu: kerumunan asli yang menjawab satu akun pemancing di menit yang sama. Inilah alasan setiap temuan
> tetap diputuskan analis.

## 7:40–8:30 · Kelayakan dan penutup (slide 11–12)

[Slide 11]

> SENTINEL ringan: Python dan SQLite, tanpa GPU dan tanpa cloud, bisa dipasang di jaringan tertutup satuan dengan satu
> perintah. Langkah berikutnya: lensa co-share untuk bot retweet, Telegram, mode near-real-time, dan deteksi meme
> duplikat.

[Slide 12]

> Bagi kami, pertanyaannya bukan "berapa banyak yang membicarakan", tetapi "siapa yang bergerak bersama". SENTINEL bisa
> dicoba sekarang di tautan ini. Terima kasih.

---

## Catatan produksi

- Rekam demo dan slide terpisah, gabungkan saat edit. Potong jeda loading.
- Perbesar (zoom 125–150 %) saat menunjuk barcode sinkronisasi dan skor.
- Jangan menampilkan data asli TikTok atau username asli di video (rulebook: data pribadi pihak ketiga).
- Unggah ke YouTube sebagai **Unlisted** atau Public, judul: "SENTINEL — Deteksi Operasi Pengaruh Terkoordinasi · Kartika Cyber Hackathon 2026".
