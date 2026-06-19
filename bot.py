import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
import os
import json
from datetime import datetime, timedelta

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "data.json"

# Menyimpan siapa yang sedang diminta upload foto bukti bayar, dan untuk sesi mana.
# Bentuk: { user_id: sesi_id }
# Ini cuma hidup di memori (hilang kalau bot restart), karena sifatnya sementara.
menunggu_bukti_bayar = {}


def load_data():
    if not os.path.exists(DATA_FILE):
        return {"sesi": {}, "sesi_terakhir_id": 0}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


def buat_sesi_baru(host_id, durasi_menit, channel_id, menu_text, menu_foto_url, catatan_sesi):
    data = load_data()
    sesi_id = data["sesi_terakhir_id"] + 1
    data["sesi_terakhir_id"] = sesi_id
    sekarang = datetime.now()
    tutup_pada = sekarang + timedelta(minutes=durasi_menit)
    data["sesi"][str(sesi_id)] = {
        "host_id": host_id,
        "channel_id": channel_id,
        "dibuka_pada": sekarang.isoformat(),
        "tutup_pada": tutup_pada.isoformat(),
        "ditutup_pada_real": None,
        "status": "terbuka",
        "menu_text": menu_text,
        "menu_foto_url": menu_foto_url,
        "catatan_sesi": catatan_sesi,
        "struk_url": None,
        "keterangan_bayar": None,
        "struk_terkirim_pada": None,
        "peserta": []
    }
    save_data(data)
    return sesi_id, tutup_pada


def ambil_sesi(sesi_id):
    data = load_data()
    return data["sesi"].get(str(sesi_id))


@bot.event
async def on_ready():
    print(f"Bot {bot.user} sudah online!")
    synced = await bot.tree.sync()
    print(f"Sync {len(synced)} slash command")
    cek_sesi_kadaluarsa.start()
    cek_reminder_susulan.start()


@bot.event
async def on_message(message):
    # Jangan proses pesan dari bot sendiri, dan jangan ganggu command prefix lama.
    if message.author.bot:
        return

    # Cek dulu apakah ini DM (bukan channel server), dan apakah user ini sedang
    # ditunggu upload bukti bayar.
    if isinstance(message.channel, discord.DMChannel) and message.author.id in menunggu_bukti_bayar:
        sesi_id = menunggu_bukti_bayar[message.author.id]

        if not message.attachments:
            await message.channel.send(
                "Mohon lampirkan foto bukti transfer ya, bukan teks biasa 🙏"
            )
            return

        lampiran = message.attachments[0]
        if not lampiran.content_type or not lampiran.content_type.startswith("image"):
            await message.channel.send(
                "File yang dilampirkan harus berupa gambar (foto bukti transfer)."
            )
            return

        data = load_data()
        sesi = data["sesi"].get(str(sesi_id))

        if sesi is None:
            await message.channel.send("Sesi tidak ditemukan, sepertinya datanya sudah tidak ada.")
            del menunggu_bukti_bayar[message.author.id]
            return

        ditemukan = False
        for p in sesi["peserta"]:
            if p["user_id"] == message.author.id:
                p["sudah_bayar"] = True
                p["bukti_bayar_url"] = lampiran.url
                ditemukan = True

        if ditemukan:
            save_data(data)
            del menunggu_bukti_bayar[message.author.id]
            await message.channel.send(
                f"Bukti transfer kamu untuk sesi #{sesi_id} sudah tercatat. Terima kasih! 🙏"
            )

            channel = bot.get_channel(sesi["channel_id"])
            if channel:
                await channel.send(
                    f"{message.author.display_name} sudah konfirmasi bayar untuk sesi #{sesi_id}, lengkap dengan bukti transfer."
                )
        else:
            await message.channel.send("Kamu belum tercatat ikut order di sesi ini.")
            del menunggu_bukti_bayar[message.author.id]

        return

    await bot.process_commands(message)


@tasks.loop(minutes=1)
async def cek_sesi_kadaluarsa():
    data = load_data()
    sekarang = datetime.now()
    ada_perubahan = False

    for sesi_id, sesi in data["sesi"].items():
        if sesi["status"] != "terbuka":
            continue

        tutup_pada = datetime.fromisoformat(sesi["tutup_pada"])
        if sekarang >= tutup_pada:
            sesi["status"] = "tertutup"
            sesi["ditutup_pada_real"] = sekarang.isoformat()
            ada_perubahan = True

            channel = bot.get_channel(sesi["channel_id"])
            if channel:
                jumlah_peserta = len(sesi["peserta"])
                await channel.send(
                    f"Sesi order #{sesi_id} otomatis ditutup (waktu habis). "
                    f"Total {jumlah_peserta} orang ikut order.\n"
                    f"Host, jangan lupa kirim struk dan info pembayaran pakai `/struk sesi_id:{sesi_id}` ya."
                )

    if ada_perubahan:
        save_data(data)


@tasks.loop(minutes=10)
async def cek_reminder_susulan():
    # Reminder susulan ini cuma berlaku untuk sesi yang strukturnya sudah dikirim,
    # dan baru aktif 24 jam setelah struk dikirim (bukan setelah sesi ditutup),
    # karena notifikasi pertama sudah terjadi tepat saat struk dikirim.
    data = load_data()
    sekarang = datetime.now()
    ada_perubahan = False

    for sesi_id, sesi in data["sesi"].items():
        if sesi.get("struk_terkirim_pada") is None:
            continue

        struk_terkirim_pada = datetime.fromisoformat(sesi["struk_terkirim_pada"])
        batas_reminder = struk_terkirim_pada + timedelta(hours=24)

        if sekarang < batas_reminder:
            continue

        for p in sesi["peserta"]:
            if p["sudah_bayar"] or p.get("sudah_diingatkan_susulan"):
                continue

            user = bot.get_user(p["user_id"])
            if user is None:
                try:
                    user = await bot.fetch_user(p["user_id"])
                except discord.NotFound:
                    continue

            pesan = (
                f"Halo {p['nama']}, ini reminder susulan untuk pesanan kamu di sesi #{sesi_id} "
                f"(**{p['menu']}**) yang belum terkonfirmasi lunas."
            )
            if sesi.get("keterangan_bayar"):
                pesan += f"\n\n**Info pembayaran:**\n{sesi['keterangan_bayar']}"
            if sesi.get("struk_url"):
                pesan += f"\n\n[Lihat struk]({sesi['struk_url']})"
            pesan += "\n\nKalau sudah transfer, klik tombol Bayar di pesan sebelumnya, atau reply pesan ini dengan foto buktinya ya 😊"

            try:
                view = BayarView(sesi_id)
                await user.send(pesan, view=view)
            except discord.Forbidden:
                pass

            p["sudah_diingatkan_susulan"] = True
            ada_perubahan = True

    if ada_perubahan:
        save_data(data)


class OrderModal(discord.ui.Modal, title="Ikut order"):
    def __init__(self, sesi_id):
        super().__init__()
        self.sesi_id = sesi_id

    menu = discord.ui.TextInput(
        label="Menu yang kamu pesan",
        placeholder="Contoh: Ayam geprek lv 3, extra nasi",
        style=discord.TextStyle.short,
        max_length=200
    )
    catatan = discord.ui.TextInput(
        label="Catatan (opsional)",
        placeholder="Contoh: sambelnya dipisah",
        style=discord.TextStyle.short,
        required=False,
        max_length=100
    )

    async def on_submit(self, interaction: discord.Interaction):
        data = load_data()
        sesi = data["sesi"].get(str(self.sesi_id))

        if sesi is None or sesi["status"] != "terbuka":
            await interaction.response.send_message(
                "Maaf, sesi ini sudah tidak aktif.",
                ephemeral=True
            )
            return

        sesi["peserta"].append({
            "user_id": interaction.user.id,
            "nama": interaction.user.display_name,
            "menu": self.menu.value,
            "catatan": self.catatan.value,
            "sudah_bayar": False,
            "sudah_diingatkan_susulan": False,
            "bukti_bayar_url": None
        })
        save_data(data)

        await interaction.response.send_message(
            f"Tercatat di sesi #{self.sesi_id}! {interaction.user.mention} ikut order: **{self.menu.value}**"
            + (f" _(catatan: {self.catatan.value})_" if self.catatan.value else ""),
        )


class OrderView(discord.ui.View):
    def __init__(self, sesi_id):
        super().__init__(timeout=None)
        self.sesi_id = sesi_id

    @discord.ui.button(label="Ikut order", style=discord.ButtonStyle.primary)
    async def ikut_order(self, interaction: discord.Interaction, button: discord.ui.Button):
        sesi = ambil_sesi(self.sesi_id)
        if sesi is None or sesi["status"] != "terbuka":
            await interaction.response.send_message(
                "Maaf, sesi ini sudah ditutup.",
                ephemeral=True
            )
            return

        tutup_pada = datetime.fromisoformat(sesi["tutup_pada"])
        if datetime.now() >= tutup_pada:
            await interaction.response.send_message(
                "Maaf, waktu sesi ini sudah habis.",
                ephemeral=True
            )
            return

        await interaction.response.send_modal(OrderModal(self.sesi_id))


class BayarView(discord.ui.View):
    """View ini dikirim lewat DM, isinya satu tombol 'Bayar' yang minta user reply foto."""

    def __init__(self, sesi_id):
        super().__init__(timeout=None)
        self.sesi_id = sesi_id

    @discord.ui.button(label="Bayar", style=discord.ButtonStyle.success)
    async def bayar(self, interaction: discord.Interaction, button: discord.ui.Button):
        sesi = ambil_sesi(self.sesi_id)

        if sesi is None:
            await interaction.response.send_message("Sesi tidak ditemukan.", ephemeral=True)
            return

        sudah_lunas = any(
            p["user_id"] == interaction.user.id and p["sudah_bayar"]
            for p in sesi["peserta"]
        )
        if sudah_lunas:
            await interaction.response.send_message(
                "Kamu sudah tercatat lunas untuk sesi ini ya, terima kasih 🙏",
                ephemeral=True
            )
            return

        menunggu_bukti_bayar[interaction.user.id] = self.sesi_id
        await interaction.response.send_message(
            "Oke! Reply pesan ini dengan foto bukti transfer kamu ya.",
            ephemeral=True
        )


@bot.tree.command(name="order", description="Buka sesi order baru")
async def order(
    interaction: discord.Interaction,
    durasi_menit: int,
    menu_text: str = "",
    menu_foto: discord.Attachment = None,
    catatan_sesi: str = ""
):
    if not menu_text and not menu_foto:
        await interaction.response.send_message(
            "Isi menu_text (link/teks menu) atau lampirkan menu_foto, minimal salah satu ya.",
            ephemeral=True
        )
        return

    menu_foto_url = menu_foto.url if menu_foto else None

    sesi_id, tutup_pada = buat_sesi_baru(
        host_id=interaction.user.id,
        durasi_menit=durasi_menit,
        channel_id=interaction.channel_id,
        menu_text=menu_text,
        menu_foto_url=menu_foto_url,
        catatan_sesi=catatan_sesi
    )

    waktu_tutup_str = tutup_pada.strftime("%H:%M")

    deskripsi = f"Dibuka oleh {interaction.user.mention}"
    if menu_text:
        deskripsi += f"\nMenu: {menu_text}"
    if catatan_sesi:
        deskripsi += f"\nCatatan: {catatan_sesi}"
    deskripsi += f"\nTutup otomatis pukul {waktu_tutup_str}"

    embed = discord.Embed(
        title=f"Sesi order #{sesi_id} dibuka",
        description=deskripsi,
        color=discord.Color.purple()
    )
    if menu_foto_url:
        embed.set_image(url=menu_foto_url)

    view = OrderView(sesi_id)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="struk", description="Kirim struk dan info pembayaran, otomatis DM semua peserta")
async def struk(interaction: discord.Interaction, sesi_id: int, foto: discord.Attachment = None, link_struk: str = "", keterangan: str = ""):
    data = load_data()
    sesi = data["sesi"].get(str(sesi_id))

    if sesi is None:
        await interaction.response.send_message(f"Sesi #{sesi_id} tidak ditemukan.")
        return

    if sesi["host_id"] != interaction.user.id:
        await interaction.response.send_message(
            "Hanya host yang membuka sesi ini yang bisa kirim struk.",
            ephemeral=True
        )
        return

    if sesi["status"] != "tertutup":
        await interaction.response.send_message(
            "Sesi ini masih terbuka. Tutup dulu sesinya sebelum kirim struk.",
            ephemeral=True
        )
        return

    if not foto and not link_struk:
        await interaction.response.send_message(
            "Lampirkan foto struk atau isi link_struk minimal salah satu ya.",
            ephemeral=True
        )
        return

    struk_url = foto.url if foto else link_struk
    sesi["struk_url"] = struk_url
    sesi["keterangan_bayar"] = keterangan
    sesi["struk_terkirim_pada"] = datetime.now().isoformat()
    save_data(data)

    embed_host = discord.Embed(
        title=f"Struk & info pembayaran sesi #{sesi_id}",
        description=keterangan if keterangan else "(tidak ada keterangan tambahan)",
        color=discord.Color.orange()
    )
    if foto:
        embed_host.set_image(url=foto.url)
    else:
        embed_host.add_field(name="Link struk", value=link_struk, inline=False)

    await interaction.response.send_message(
        content="Struk sudah disimpan, dan sedang dikirim ke semua peserta lewat DM.",
        embed=embed_host
    )

    # Kirim DM ke semua peserta yang belum lunas
    gagal_kirim = []
    for p in sesi["peserta"]:
        if p["sudah_bayar"]:
            continue

        user = bot.get_user(p["user_id"])
        if user is None:
            try:
                user = await bot.fetch_user(p["user_id"])
            except discord.NotFound:
                continue

        pesan = (
            f"Halo {p['nama']}! Pesanan sesi order #{sesi_id} sudah datang.\n\n"
            f"**Pesananmu:** {p['menu']}\n"
        )
        if keterangan:
            pesan += f"\n**Info pembayaran:**\n{keterangan}\n"

        embed_dm = discord.Embed(description=pesan, color=discord.Color.orange())
        if foto:
            embed_dm.set_image(url=foto.url)
        elif link_struk:
            embed_dm.add_field(name="Link struk", value=link_struk, inline=False)

        try:
            view = BayarView(sesi_id)
            await user.send(embed=embed_dm, view=view)
        except discord.Forbidden:
            gagal_kirim.append(p["nama"])

    if gagal_kirim:
        await interaction.followup.send(
            f"Catatan: gagal kirim DM ke {', '.join(gagal_kirim)} (kemungkinan DM mereka tertutup).",
            ephemeral=True
        )


class LihatBuktiSelect(discord.ui.Select):
    def __init__(self, sesi_id, peserta_dengan_bukti):
        self.sesi_id = sesi_id
        options = [
            discord.SelectOption(label=p["nama"], description=p["menu"][:90])
            for p in peserta_dengan_bukti
        ]
        super().__init__(
            placeholder="Pilih nama untuk lihat foto bukti transfer",
            options=options
        )

    async def callback(self, interaction: discord.Interaction):
        sesi = ambil_sesi(self.sesi_id)
        if sesi is None:
            await interaction.response.send_message("Sesi tidak ditemukan.", ephemeral=True)
            return

        nama_dipilih = self.values[0]
        p = next((x for x in sesi["peserta"] if x["nama"] == nama_dipilih), None)

        if p is None or not p.get("bukti_bayar_url"):
            await interaction.response.send_message(
                f"Tidak ada foto bukti untuk {nama_dipilih}.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"Bukti transfer — {p['nama']}",
            description=f"Sesi #{self.sesi_id} — {p['menu']}",
            color=discord.Color.green()
        )
        embed.set_image(url=p["bukti_bayar_url"])
        await interaction.response.send_message(embed=embed, ephemeral=True)


class StatusView(discord.ui.View):
    def __init__(self, sesi_id, peserta_dengan_bukti):
        super().__init__(timeout=None)
        if peserta_dengan_bukti:
            self.add_item(LihatBuktiSelect(sesi_id, peserta_dengan_bukti))


@bot.tree.command(name="status", description="Lihat daftar peserta, status bayar, dan bukti transfer")
async def status(interaction: discord.Interaction, sesi_id: int):
    sesi = ambil_sesi(sesi_id)

    if sesi is None:
        await interaction.response.send_message(f"Sesi #{sesi_id} tidak ditemukan.")
        return

    if not sesi["peserta"]:
        await interaction.response.send_message(f"Belum ada yang ikut order di sesi #{sesi_id}.")
        return

    lines = []
    jumlah_lunas = 0
    peserta_dengan_bukti = []
    for p in sesi["peserta"]:
        if p["sudah_bayar"]:
            jumlah_lunas += 1
            status_bayar = "✅ lunas"
            if p.get("bukti_bayar_url"):
                status_bayar += " (ada bukti, pilih di dropdown ⬇️)"
                peserta_dengan_bukti.append(p)
        else:
            status_bayar = "⏳ belum bayar"
        lines.append(f"• {p['nama']} — {p['menu']} ({status_bayar})")

    lines.append(f"\n**Ringkasan: {jumlah_lunas}/{len(sesi['peserta'])} sudah lunas**")

    embed = discord.Embed(
        title=f"Status sesi #{sesi_id} ({sesi['status']})",
        description="\n".join(lines),
        color=discord.Color.teal()
    )

    if sesi.get("struk_url"):
        embed.add_field(name="Struk & pembayaran", value=sesi.get("keterangan_bayar") or "-", inline=False)

    view = StatusView(sesi_id, peserta_dengan_bukti)
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="tutup", description="Tutup sesi order secara manual")
async def tutup(interaction: discord.Interaction, sesi_id: int):
    data = load_data()
    sesi = data["sesi"].get(str(sesi_id))

    if sesi is None:
        await interaction.response.send_message(f"Sesi #{sesi_id} tidak ditemukan.")
        return

    if sesi["host_id"] != interaction.user.id:
        await interaction.response.send_message(
            "Hanya host yang membuka sesi ini yang bisa menutupnya.",
            ephemeral=True
        )
        return

    sesi["status"] = "tertutup"
    sesi["ditutup_pada_real"] = datetime.now().isoformat()
    save_data(data)
    await interaction.response.send_message(
        f"Sesi #{sesi_id} sudah ditutup. Tidak ada lagi yang bisa ikut order.\n"
        f"Jangan lupa kirim struk dan info pembayaran pakai `/struk sesi_id:{sesi_id}` ya."
    )


bot.run(TOKEN)
