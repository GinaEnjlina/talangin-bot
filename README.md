# 🛵 Talangin

Bot Discord untuk membantu group order kantor — mencatat siapa ikut order, mengingatkan otomatis yang belum bayar, dan menyimpan bukti transfer. Dibuat supaya host yang menalangi pembayaran tidak perlu menagih satu-satu secara manual.

## Latar Belakang

Di kantor, group order makanan (misalnya lewat ShopeeFood) sering dilakukan karena ada diskon kalau pesan banyak sekaligus. Tapi prosesnya selalu menyulitkan satu orang: **host**, yang harus menalangi dana di awal, lalu menagih kembali ke semua orang lewat chat — yang sering berakhir dengan beberapa orang lupa bayar dan host yang sungkan menagih.

Talangin mengambil alih dua peran paling melelahkan itu: **mencatat** siapa pesan apa, dan **mengingatkan** secara otomatis siapa yang belum bayar, supaya host tidak perlu jadi "penagih utang" ke rekan kerja sendiri.

## Fitur

- 📝 Catat peserta order lewat tombol dan modal form, bukan reply chat manual
- 🖼️ Mendukung menu berupa link, foto, atau keduanya
- ⏰ Sesi order otomatis tertutup sesuai durasi yang ditentukan host
- 🧾 Host kirim struk (foto/link) + info pembayaran setelah pesanan datang
- 📩 Bot otomatis DM semua peserta yang belum bayar begitu struk dikirim
- 💸 Konfirmasi bayar dengan bukti foto transfer, bukan asal klik tanpa bukti
- 🔁 Reminder susulan otomatis 24 jam kemudian kalau masih belum ada konfirmasi
- 📊 Dashboard `/status` dengan dropdown untuk melihat bukti transfer tiap peserta
- ❓ Command `/bantuan` berisi panduan lengkap, hanya terlihat oleh yang mengetik

## Alur Penggunaan

### Untuk Host

1. `/order` — buka sesi baru, isi durasi, menu (teks/foto), dan catatan opsional
2. Tunggu peserta klik tombol **Ikut order** sampai waktu habis
3. Sesi otomatis tertutup, host checkout dan bayar di luar bot
4. `/struk` — kirim foto/link struk beserta info pembayaran (rekening/e-wallet)
5. Bot otomatis DM semua peserta yang belum bayar, lengkap dengan tombol **Bayar**
6. `/status` — pantau siapa sudah/belum bayar, cek bukti transfer lewat dropdown
7. `/tutup` — opsional, untuk menutup sesi lebih cepat dari jadwal

### Untuk Peserta

1. Klik tombol **Ikut order** di pesan sesi, isi menu yang dipesan
2. Tunggu DM otomatis dari bot setelah host mengirim struk
3. Klik tombol **Bayar** di DM tersebut, transfer sesuai info yang diberikan
4. Reply DM itu dengan foto bukti transfer
5. Status otomatis berubah lunas, dan tidak akan menerima reminder lagi

## Daftar Command

| Command | Pengguna | Keterangan |
|---|---|---|
| `/order` | Host | Membuka sesi order baru |
| `/struk` | Host | Mengirim struk dan info pembayaran, memicu DM ke semua peserta |
| `/status` | Siapa saja | Melihat daftar peserta, status bayar, dan bukti transfer |
| `/tutup` | Host | Menutup sesi order secara manual |
| `/bantuan` | Siapa saja | Menampilkan panduan penggunaan (hanya terlihat oleh pengirim) |

## Tech Stack

- **Python 3** dengan [discord.py](https://discordpy.readthedocs.io/)
- Penyimpanan data menggunakan file **JSON** lokal (`data.json`)
- **Slash command**, **button**, **modal form**, dan **select menu** native Discord
- **Background task** (`discord.ext.tasks`) untuk penutupan sesi otomatis dan reminder berjenjang



## Keterbatasan & Rencana Lanjutan

- Data disimpan dalam file JSON lokal, belum menggunakan database — cukup untuk skala tim kecil, tapi rawan konflik kalau diakses bersamaan dalam volume tinggi
- Status "sedang menunggu upload bukti" tersimpan di memori, bukan persisten — akan hilang kalau bot restart di tengah proses
- Belum ada verifikasi otomatis terhadap foto bukti transfer (sepenuhnya self-report, divalidasi visual oleh host secara manual)
- Belum mendukung multi-host bergilir dalam satu sesi

## Latar Belakang Proyek

Talangin awalnya dirancang sebagai studi kasus produk untuk portofolio UI/UX, lalu dikembangkan menjadi bot yang benar-benar berfungsi sebagai latihan memahami bagaimana keputusan desain diterjemahkan ke batasan teknis platform nyata.
