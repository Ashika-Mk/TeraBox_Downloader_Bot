def format_progress_bar(filename, percentage, done, total_size, status, eta, speed, elapsed, user_mention, user_id, aria2p_gid):
    bar_length = 10
    filled_length = int(bar_length * percentage / 100)
    bar = '▰' * filled_length + '▱' * (bar_length - filled_length)
    def format_size(size):
        size = int(size)
        if size < 1024:
            return f"{size} B"
        elif size < 1024 ** 2:
            return f"{size / 1024:.2f} KB"
        elif size < 1024 ** 3:
            return f"{size / 1024 ** 2:.2f} MB"
        else:
            return f"{size / 1024 ** 3:.2f} GB"
    
    def format_time(seconds):
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds} sec"
        elif seconds < 3600:
            return f"{seconds // 60} min"
        else:
            hours = seconds // 3600
            minutes = (seconds % 3600) // 60
            return f"{hours} hr {minutes} min"
    
    return (
        f"┏🕵️ Fɪʟᴇɴᴀᴍᴇ : {filename}\n"
        f"┠ [{bar}] {percentage:.2f}%\n"
        f"┠🔄 Pʀᴏᴄᴇssᴇᴅ : {format_size(done)} ᴏғ {format_size(total_size)}\n"
        f"┠📶 Sᴛᴀᴛᴜs : {status}\n"
        f"┠⚡ Sᴘᴇᴇᴅ : {format_size(speed)}/s\n"
        f"┖👷🏻‍♂️ Usᴇʀ : {user_mention} |⏰ Iᴅ : {user_id}" 
    )
