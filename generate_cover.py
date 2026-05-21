import os
import random
import requests
import base64
from datetime import datetime
from PIL import Image, ImageFilter, ImageDraw, ImageFont

from config import UPLOAD_TO_EMBY, COVER_STYLE, LIBRARY_MAP, CONFIG, EMBY_CONFIG

# ==========================================
# 1. Emby API 基础与下载工具
# ==========================================

def get_emby_item_id(library_name):
    url = f"{EMBY_CONFIG['url']}/emby/Items"
    params = {
        "api_key": EMBY_CONFIG["api_key"],
        "Recursive": "true",
        "IncludeItemTypes": "CollectionFolder,BoxSet"
    }
    try:
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            items = response.json().get("Items", [])
            for item in items:
                if item.get("Name") == library_name:
                    return item.get("Id")
    except Exception as e:
        print(f"❌ 连接 Emby API 失败: {e}")
    return None

def download_image(url, save_path):
    try:
        response = requests.get(url, stream=True, timeout=(10, 20))
        if response.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
            return True
    except Exception as e:
        pass
    return False

def add_rounded_corners(im, rad):
    circle = Image.new('L', (rad * 2, rad * 2), 0)
    draw = ImageDraw.Draw(circle)
    draw.ellipse((0, 0, rad * 2 - 1, rad * 2 - 1), fill=255)
    alpha = Image.new('L', im.size, 255)
    w, h = im.size
    alpha.paste(circle.crop((0, 0, rad, rad)), (0, 0))
    alpha.paste(circle.crop((0, rad, rad, rad * 2)), (0, h - rad))
    alpha.paste(circle.crop((rad, 0, rad * 2, rad)), (w - rad, 0))
    alpha.paste(circle.crop((rad, rad, rad * 2, rad * 2)), (w - rad, h - rad))
    im.putalpha(alpha)
    return im

def upload_cover_to_emby(item_id, image_path):
    url = f"{EMBY_CONFIG['url']}/emby/Items/{item_id}/Images/Primary"
    params = {"api_key": EMBY_CONFIG["api_key"]}
    print(f"☁️ 正在同步封面至 Emby...")
    try:
        with open(image_path, "rb") as img_file:
            b64_data = base64.b64encode(img_file.read())
        headers = {"Content-Type": "image/jpeg"}
        response = requests.post(url, params=params, headers=headers, data=b64_data, timeout=30)
        if response.status_code in [200, 204]:
            print("✅ 成功同步封面！")
        else:
            print(f"❌ 上传失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ 同步异常: {e}")

# ==========================================
# 2. Style 1 引擎 (经典平铺瀑布流)
# ==========================================

def fetch_s1_images(library_name):
    lib_id = get_emby_item_id(library_name)
    if not lib_id: return False, None, []

    url = f"{EMBY_CONFIG['url']}/emby/Items"
    params = {
        "api_key": EMBY_CONFIG["api_key"], "ParentId": lib_id, "Recursive": "true",
        "IncludeItemTypes": "Movie,Series", "SortBy": "DateCreated", "SortOrder": "Descending",
        "Limit": 20, "Fields": "BackdropImageTags"       
    }
    items = requests.get(url, params=params, timeout=10).json().get("Items", [])
    
    target_count = CONFIG["s1_poster_count"]
    if len(items) < target_count: return False, None, []

    os.makedirs("./input", exist_ok=True)
    bg_path = "./input/s1_bg.jpg"
    poster_paths = []
    bg_success, used_bg_id = False, None
    
    for item in items:
        if item.get("BackdropImageTags"):
            url = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Backdrop/0?api_key={EMBY_CONFIG['api_key']}&maxWidth=1920"
        else:
            url = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Primary?api_key={EMBY_CONFIG['api_key']}&maxWidth=1920"
        if download_image(url, bg_path):
            bg_success = True
            used_bg_id = item['Id']
            break 

    if not bg_success: return False, None, []

    for item in [it for it in items if it['Id'] != used_bg_id]:
        if len(poster_paths) >= target_count: break 
        p_path = f"./input/s1_p_{len(poster_paths)+1}.jpg"
        p_url = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Primary?api_key={EMBY_CONFIG['api_key']}&maxWidth=600"
        if download_image(p_url, p_path): poster_paths.append(p_path)

    if len(poster_paths) < target_count: return False, None, []
    return True, bg_path, poster_paths

def render_s1_cover(bg_path, poster_paths, lib_key, output_path):
    print("🎨 正在渲染 [Style 1] 经典平铺封面...")
    bg = Image.open(bg_path).convert("RGBA").resize(CONFIG["output_size"], Image.Resampling.LANCZOS)
    
    blur_rad = max(0, min(100, CONFIG["s1_blur_percent"])) / 100.0 * 30
    if blur_rad > 0: bg = bg.filter(ImageFilter.GaussianBlur(blur_rad))

    if CONFIG["s1_snow_enable"]:
        snow = Image.new('RGBA', bg.size, (0,0,0,0))
        d_snow = ImageDraw.Draw(snow)
        for _ in range(CONFIG["s1_snow_density"]):
            x, y = random.randint(0, bg.size[0]), random.randint(0, bg.size[1])
            r = random.randint(*CONFIG["s1_snow_size_range"])
            a = random.randint(*CONFIG["s1_snow_alpha_range"])
            d_snow.ellipse((x-r, y-r, x+r, y+r), fill=(255,255,255,a))
        bg = Image.alpha_composite(bg, snow)

    grad = Image.new('RGBA', bg.size, (0,0,0,0))
    d_grad = ImageDraw.Draw(grad)
    f_w, m_a = CONFIG["s1_gradient_width"], CONFIG["s1_gradient_max_alpha"]
    for x in range(f_w):
        d_grad.line((x, 0, x, bg.size[1]), fill=(0,0,0, int(m_a*(1-(x/f_w)))))
    bg = Image.alpha_composite(bg, grad)

    draw = ImageDraw.Draw(bg)
    lib_n = LIBRARY_MAP.get(lib_key, {"zh": "未知", "en": "UNKNOWN"})
    f_zh = ImageFont.truetype(CONFIG["font_zh_path"], CONFIG["s1_font_size_zh"])
    f_en = ImageFont.truetype(CONFIG["font_en_path"], CONFIG["s1_font_size_en"])
    
    draw.text(CONFIG["s1_text_pos_zh"], lib_n["zh"], font=f_zh, fill=(255,255,255,255))
    draw.text(CONFIG["s1_text_pos_en"], lib_n["en"], font=f_en, fill=(255,255,255,255), spacing=15)

    start_x = (CONFIG["output_size"][0] - (CONFIG["s1_poster_size"][0]*6 + CONFIG["s1_poster_spacing"]*5)) // 2
    for i, p in enumerate(poster_paths):
        img = add_rounded_corners(Image.open(p).convert("RGBA").resize(CONFIG["s1_poster_size"], Image.Resampling.LANCZOS), 15)
        bg.paste(img, (start_x + i*(CONFIG["s1_poster_size"][0]+CONFIG["s1_poster_spacing"]), CONFIG["s1_poster_y_pos"]), img)
        
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bg.convert("RGB").save(output_path, quality=92)
    return True

# ==========================================
# 3. Style 2 引擎 (倾斜阶梯海报墙)
# ==========================================

def fetch_s2_images(library_name):
    lib_id = get_emby_item_id(library_name)
    if not lib_id: return False, []

    url = f"{EMBY_CONFIG['url']}/emby/Items"
    params = {
        "api_key": EMBY_CONFIG["api_key"], "ParentId": lib_id, "Recursive": "true",
        "IncludeItemTypes": "Movie,Series", "SortBy": "DateCreated", "SortOrder": "Descending", "Limit": 25
    }
    items = requests.get(url, params=params, timeout=10).json().get("Items", [])
    
    target_count = CONFIG["s2_poster_count"]
    if len(items) < target_count: return False, []

    os.makedirs("./input", exist_ok=True)
    poster_paths = []
    
    for item in items:
        if len(poster_paths) >= target_count: break 
        p_path = f"./input/s2_p_{len(poster_paths)+1}.jpg"
        p_url = f"{EMBY_CONFIG['url']}/emby/Items/{item['Id']}/Images/Primary?api_key={EMBY_CONFIG['api_key']}&maxWidth=600"
        if download_image(p_url, p_path): poster_paths.append(p_path)

    if len(poster_paths) < target_count: return False, []
    return True, poster_paths

def render_s2_cover(poster_paths, lib_key, output_path):
    print("🎨 正在渲染 [Style 2] 倾斜阶梯封面...")
    bg_c = CONFIG["s2_bg_default_color"]
    if CONFIG["s2_bg_auto_color"]:
        try:
            c = Image.open(poster_paths[0]).convert('RGB').resize((1,1)).getpixel((0,0))
            bg_c = tuple(max(0, int(v * 0.7)) for v in c)
        except: pass

    cv = Image.new("RGBA", CONFIG["output_size"], bg_c + (255,))
    wl = Image.new("RGBA", (3000, 3000), (0,0,0,0))
    p_w, p_h = CONFIG["s2_poster_size"]
    
    for i, path in enumerate(poster_paths):
        col, row = i // 3, i % 3
        try:
            img = add_rounded_corners(Image.open(path).convert("RGBA").resize((p_w, p_h), Image.Resampling.LANCZOS), 25)
            x = col * (p_w + CONFIG["s2_poster_spacing_x"])
            y = row * (p_h + CONFIG["s2_poster_spacing_y"]) + (col * CONFIG["s2_poster_stagger"])
            wl.paste(img, (x, y), img)
        except: pass

    rt = wl.rotate(CONFIG["s2_poster_rotation"], expand=True, resample=Image.Resampling.BICUBIC)
    cv.paste(rt, CONFIG["s2_poster_grid_pos"], rt)

    d = ImageDraw.Draw(cv)
    lib_n = LIBRARY_MAP.get(lib_key, {"zh": "未知", "en": "UNKNOWN"})
    f_zh = ImageFont.truetype(CONFIG["font_zh_path"], CONFIG["s2_font_size_zh"])
    f_en = ImageFont.truetype(CONFIG["font_en_path"], CONFIG["s2_font_size_en"])
    tx, ty = CONFIG["s2_text_pos"]
    
    d.text((tx, ty), lib_n["zh"], font=f_zh, fill=(255,255,255,255))
    en_y = ty + CONFIG["s2_font_size_zh"] + 25
    
    if CONFIG["s2_accent_bar_enable"]:
        bw, bh = 15, CONFIG["s2_font_size_en"] - 5
        d.rectangle([tx, en_y+10, tx+bw, en_y+10+bh], fill=CONFIG["s2_accent_bar_color"])
        d.text((tx+bw+25, en_y), lib_n["en"], font=f_en, fill=(255,255,255,255))
    else:
        d.text((tx, en_y), lib_n["en"], font=f_en, fill=(255,255,255,255))

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    cv.convert("RGB").save(output_path, quality=92)
    return True

# ==========================================
# 4. 任务执行调度
# ==========================================

def run_job():
    print(f"\n========== Emby Cover Generator (双擎版) ==========")
    print(f"当前模式: [{COVER_STYLE}] | 时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    if EMBY_CONFIG["api_key"] == "YOUR_API_KEY_HERE":
        print("❌ 请配置真实的 EMBY_URL 和 EMBY_API_KEY！")
        return

    for lib_key in list(LIBRARY_MAP.keys()):
        print(f"\n>>> 处理媒体库: [{lib_key}] <<<")
        target_zh_name = LIBRARY_MAP[lib_key]["zh"]
        out_img = f"./output/cover_{lib_key}.jpg"
        
        if COVER_STYLE == "style_1":
            success, bg_img, posters = fetch_s1_images(target_zh_name)
            if success and render_s1_cover(bg_img, posters, lib_key, out_img):
                if UPLOAD_TO_EMBY: upload_cover_to_emby(get_emby_item_id(target_zh_name), out_img)
                else: print(f"⚠️ [预览] {out_img} 已保存。")
                
        elif COVER_STYLE == "style_2":
            success, posters = fetch_s2_images(target_zh_name)
            if success and render_s2_cover(posters, lib_key, out_img):
                if UPLOAD_TO_EMBY: upload_cover_to_emby(get_emby_item_id(target_zh_name), out_img)
                else: print(f"⚠️ [预览] {out_img} 已保存。")
        else:
            print(f"❌ 未知的封面样式: {COVER_STYLE}")
            break

    print("\n================ 任务结束 ================\n")

if __name__ == "__main__":
    run_job()
