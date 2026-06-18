import os
import glob
import re
from datetime import datetime, timedelta
import pandas as pd
import streamlit as st
import yfinance as yf

# 設定網頁介面為寬屏模式
st.set_page_config(layout="wide", page_title="美股兩日動態數據對比工具")

def get_all_local_csvs():
    """搜尋當前資料夾下所有符合格式的 CSV，依檔名日期從新到舊排序"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    search_pattern = os.path.join(script_dir, "new_*.csv")
    csv_files = glob.glob(search_pattern)
    if csv_files:
        csv_files.sort(reverse=True)
        return csv_files
    return []

def push_to_github_backend(file_name, file_bytes):
    """【後台自動化核心】將網頁收到的 CSV 即時經後台 Commit & Push 回 GitHub"""
    if "GITHUB_TOKEN" not in st.secrets:
        return False
        
    try:
        from github import Github
        token = st.secrets["GITHUB_TOKEN"]
        repo_name = "kinaoc-ui/shock"  # 你的專案路徑
        
        g = Github(token)
        repo = g.get_repo(repo_name)
        
        # 檢查 GitHub 內原本有冇同名檔案，有就覆蓋，冇就新建
        try:
            contents = repo.get_contents(file_name)
            repo.update_file(contents.path, f"Auto-update {file_name} via web", file_bytes, contents.sha)
        except:
            repo.create_file(file_name, f"Auto-upload {file_name} via web", file_bytes)
        return True
    except Exception as e:
        st.warning(f"後台自動備份到 GitHub 失敗（但不影響本次運算）: {e}")
        return False

def trigger_sync(uploaded_file):
    """觸發後台同步機制（利用 Session State 防止重複提交）"""
    if st.session_state.get(f"synced_{uploaded_file.name}") is None:
        if push_to_github_backend(uploaded_file.name, uploaded_file.getvalue()):
            st.session_state[f"synced_{uploaded_file.name}"] = True
            st.toast(f"🚀 {uploaded_file.name} 已成功自動上傳並永久儲存至 GitHub！", icon="✨")

def load_and_clean_csv(file_path_or_buffer):
    """讀取 CSV 並清洗欄位名稱與代號（含缺失欄位自動補底）"""
    try:
        df = pd.read_csv(file_path_or_buffer)
        df.rename(columns={df.columns[0]: 'Symbol'}, inplace=True)
        df['Symbol'] = df['Symbol'].astype(str).str.strip()
        
        standard_cols = {
            'description': 'Description',
            'price': 'Price',
            'sector': 'Sector',
            'industry': 'Industry',
            'market capitalization': 'Market capitalization',
            'price to earnings ratio': 'Price to earnings ratio'
        }
        
        rename_dict = {}
        for col in df.columns:
            cleaned_col = str(col).strip().lower()
            if cleaned_col in standard_cols:
                rename_dict[col] = standard_cols[cleaned_col]
        
        df.rename(columns=rename_dict, inplace=True)
        
        if 'Description' not in df.columns: df['Description'] = 'N/A'
        if 'Price' not in df.columns: df['Price'] = 0.0
        if 'Sector' not in df.columns: df['Sector'] = 'Unclassified'
        if 'Industry' not in df.columns: df['Industry'] = 'Unclassified'
        if 'Market capitalization' not in df.columns: df['Market capitalization'] = 0
        if 'Price to earnings ratio' not in df.columns: df['Price to earnings ratio'] = 0
            
        return df
    except Exception as e:
        st.error(f"讀取數據失敗: {e}")
        return None

def fetch_sp500_historical_returns(dates):
    """
    極速獲取 S&P 500 對應日期的真實收益率。
    採用業界最穩健的 SPY (S&P 500 ETF) 作為代理。
    """
    sp500_returns = {}
    if not dates:
        return sp500_returns
        
    try:
        dt_list = []
        for d in dates:
            try:
                dt_list.append(datetime.strptime(d, "%Y-%m-%d"))
            except:
                continue
        if not dt_list:
            return sp500_returns
            
        start_date = (min(dt_list) - timedelta(days=5)).strftime("%Y-%m-%d")
        end_date = (max(dt_list) + timedelta(days=5)).strftime("%Y-%m-%d")
        
        spy = yf.Ticker("SPY")
        hist = spy.history(start=start_date, end=end_date)
        
        if hist.empty:
            spy = yf.Ticker("^GSPC")
            hist = spy.history(start=start_date, end=end_date)
            
        if not hist.empty:
            hist['Daily_Return'] = hist['Close'].pct_change() * 100
            for dt in dt_list:
                date_str = dt.strftime("%Y-%m-%d")
                temp_hist = hist.loc[hist.index.strftime('%Y-%m-%d') == date_str]
                if not temp_hist.empty:
                    sp500_returns[date_str] = temp_hist['Daily_Return'].values[0]
                else:
                    closest_idx = hist.index.asof(dt)
                    if pd.notna(closest_idx):
                        sp500_returns[date_str] = hist.loc[closest_idx, 'Daily_Return']
                    else:
                        sp500_returns[date_str] = 0.0
    except Exception as e:
        for d in dates:
            sp500_returns[d] = 0.0
    return sp500_returns

def fetch_live_market_data(symbols):
    """全自動連線 Yahoo Finance 抓取盤前/盤後即時價格及變幅"""
    live_data = {}
    if not symbols:
        return live_data
        
    try:
        tickers = yf.Tickers(' '.join(symbols))
        for sym in symbols:
            try:
                info = tickers.tickers[sym].info
                state = "常規"
                current_price = info.get('regularMarketPrice')
                prev_close = info.get('previousClose', 1)
                
                if info.get('preMarketPrice'):
                    current_price = info.get('preMarketPrice')
                    state = "盤前 🌅"
                elif info.get('postMarketPrice'):
                    current_price = info.get('postMarketPrice')
                    state = "盤後 🌃"
                
                if current_price and prev_close:
                    live_pct = ((current_price - prev_close) / prev_close) * 100
                    live_data[sym] = {
                        '即時市況': state,
                        '最新即時價': current_price,
                        '即時總變幅 %': live_pct
                    }
            except:
                continue
    except Exception as e:
        st.warning(f"即時盤前數據獲取失敗: {e}")
    return live_data

def generate_tradingview_watchlist_content(df_added, df_removed, top_gainers, top_losers):
    """純記憶體生成 TradingView 專用導入格式的文字內容"""
    if df_added.empty and df_removed.empty and top_gainers.empty and top_losers.empty:
        return ""

    output = []
    
    if not top_gainers.empty:
        df_tg = top_gainers.copy()
        df_tg['部門板塊'] = df_tg['部門板塊'].fillna('Unclassified').astype(str).str.strip()
        df_tg['行業'] = df_tg['行業'].fillna('Unclassified').astype(str).str.strip()
        tg_groups = df_tg.groupby(['部門板塊', '行業'])
        for (sector, industry), group in tg_groups:
            output.append(f"### Top_Gainers — {sector} — {industry}\n")
            for symbol in group['Symbol']: output.append(f"{symbol}\n")
            output.append("\n")

    if not top_losers.empty:
        df_tl = top_losers.copy()
        df_tl['部門板塊'] = df_tl['部門板塊'].fillna('Unclassified').astype(str).str.strip()
        df_tl['行業'] = df_tl['行業'].fillna('Unclassified').astype(str).str.strip()
        tl_groups = df_tl.groupby(['部門板塊', '行業'])
        for (sector, industry), group in tl_groups:
            output.append(f"### Top_Losers — {sector} — {industry}\n")
            for symbol in group['Symbol']: output.append(f"{symbol}\n")
            output.append("\n")

    if not df_added.empty:
        df_ad = df_added.copy()
        df_ad['部門板塊'] = df_ad['部門板塊'].fillna('Unclassified').astype(str).str.strip()
        df_ad['行業'] = df_ad['行業'].fillna('Unclassified').astype(str).str.strip()
        added_groups = df_ad.groupby(['部門板塊', '行業'])
        for (sector, industry), group in added_groups:
            output.append(f"### up_{sector} — {industry}\n")
            for symbol in group['Symbol']: output.append(f"{symbol}\n")
            output.append("\n")

    if not df_removed.empty:
        df_rm = df_removed.copy()
        df_rm['部門板塊'] = df_rm['部門板塊'].fillna('Unclassified').astype(str).str.strip()
        df_rm['行業'] = df_rm['行業'].fillna('Unclassified').astype(str).str.strip()
        removed_groups = df_rm.groupby(['部門板塊', '行業'])
        for (sector, industry), group in removed_groups:
            output.append(f"### down_{sector} — {industry}\n")
            for symbol in group['Symbol']: output.append(f"{symbol}\n")
            output.append("\n")
            
    return "".join(output)

def calculate_recent_7_days_trends(local_files, active_df_new, active_df_old, active_date_str):
    """融合當前運算日與雲端歷史紀錄，計算近 7 個交易日的板塊新增/剔除統計矩陣"""
    added_records = []
    removed_records = []
    
    set_new = set(active_df_new['Symbol'])
    set_old = set(active_df_old['Symbol'])
    
    df_a = active_df_new[active_df_new['Symbol'].isin(set_new - set_old)]
    if not df_a.empty:
        for sector, count in df_a['Sector'].value_counts().items():
            added_records.append({'Date': active_date_str, 'Sector': sector, 'Count': count})
            
    df_r = active_df_old[active_df_old['Symbol'].isin(set_old - set_new)]
    if not df_r.empty:
        for sector, count in df_r['Sector'].value_counts().items():
            removed_records.append({'Date': active_date_str, 'Sector': sector, 'Count': count})
            
    processed_dates = {active_date_str}
    pairs_counted = 1
    
    for i in range(len(local_files) - 1):
        if pairs_counted >= 7:
            break
            
        f_new = local_files[i]
        f_old = local_files[i+1]
        
        m = re.search(r'new_(\d{4}-\d{2}-\d{2})', os.path.basename(f_new))
        date_str = m.group(1) if m else os.path.basename(f_new).replace("new_", "").replace(".csv", "")
        
        if date_str in processed_dates:
            continue
            
        df_n = load_and_clean_csv(f_new)
        df_o = load_and_clean_csv(f_old)
        if df_n is None or df_o is None:
            continue
            
        s_n = set(df_n['Symbol'])
        s_o = set(df_o['Symbol'])
        
        df_a_h = df_n[df_n['Symbol'].isin(s_n - s_o)]
        if not df_a_h.empty:
            for sector, count in df_a_h['Sector'].value_counts().items():
                added_records.append({'Date': date_str, 'Sector': sector, 'Count': count})
                
        df_r_h = df_o[df_o['Symbol'].isin(s_o - s_n)]
        if not df_r_h.empty:
            for sector, count in df_r_h['Sector'].value_counts().items():
                removed_records.append({'Date': date_str, 'Sector': sector, 'Count': count})
                
        processed_dates.add(date_str)
        pairs_counted += 1
        
    df_add_hm, df_rem_hm = pd.DataFrame(), pd.DataFrame()
    
    if added_records:
        df_add_all = pd.DataFrame(added_records)
        df_add_hm = df_add_all.pivot(index='Sector', columns='Date', values='Count').fillna(0).astype(int)
        df_add_hm = df_add_hm[sorted(df_add_hm.columns)]
        df_add_hm['總計'] = df_add_hm.sum(axis=1)
        df_add_hm = df_add_hm.sort_values(by='總計', ascending=False)
        df_add_hm.index.name = '部門板塊'
        
    if removed_records:
        df_rem_all = pd.DataFrame(removed_records)
        df_rem_hm = df_rem_all.pivot(index='Sector', columns='Date', values='Count').fillna(0).astype(int)
        df_rem_hm = df_rem_hm[sorted(df_rem_hm.columns)]
        df_rem_hm['總計'] = df_rem_hm.sum(axis=1)
        df_rem_hm = df_rem_hm.sort_values(by='總計', ascending=False)
        df_rem_hm.index.name = '部門板塊'
        
    return df_add_hm, df_rem_hm

def calculate_recent_7_days_performance(local_files, active_df_new, active_df_old, active_date_str, group_by_col='Sector'):
    """
    【全新革命性算法】：
    1. 拒絕攤薄！全面改用『幾何複利累積回報率』計算。
    2. 自動抓取標普 500 (SPY) 作為基準，扣除大盤表現。
    3. 加入動態 group_by_col，完美支援 Sector 或 Industry 兩種維度。
    """
    day_pairs = []
    day_pairs.append((active_df_new, active_df_old, active_date_str))
    
    processed_dates = {active_date_str}
    pairs_counted = 1
    
    for i in range(len(local_files) - 1):
        if pairs_counted >= 7:
            break
        f_new = local_files[i]
        f_old = local_files[i+1]
        
        m = re.search(r'new_(\d{4}-\d{2}-\d{2})', os.path.basename(f_new))
        date_str = m.group(1) if m else os.path.basename(f_new).replace("new_", "").replace(".csv", "")
        
        if date_str in processed_dates:
            continue
            
        df_n = load_and_clean_csv(f_new)
        df_o = load_and_clean_csv(f_old)
        if df_n is not None and df_o is not None:
            day_pairs.append((df_n, df_o, date_str))
            processed_dates.add(date_str)
            pairs_counted += 1
            
    all_dates = [pair[2] for pair in day_pairs]
    sp500_history = fetch_sp500_historical_returns(all_dates)
    
    daily_alpha_records = []
    
    for df_n, df_o, date_str in day_pairs:
        common = list(set(df_n['Symbol']) & set(df_o['Symbol']))
        if not common:
            continue
            
        # 這裡改為撈取動態傳入的欄位 (Sector 或是 Industry)
        df_n_sub = df_n[df_n['Symbol'].isin(common)][['Symbol', 'Price', group_by_col]]
        df_o_sub = df_o[df_o['Symbol'].isin(common)][['Symbol', 'Price']]
        df_m = pd.merge(df_n_sub, df_o_sub, on='Symbol', suffixes=('_new', '_old'))
        df_m = df_m[df_m['Price_old'] > 0]
        
        df_m['Change_Pct'] = ((df_m['Price_new'] - df_m['Price_old']) / df_m['Price_old']) * 100
        sp500_bench = sp500_history.get(date_str, 0.0)
        
        # 這裡改為依照動態欄位分組
        for group_name, avg_val in df_m.groupby(group_by_col)['Change_Pct'].mean().items():
            alpha_val = avg_val - sp500_bench
            daily_alpha_records.append({
                'Date': date_str,
                'Group_Name': group_name,
                'Alpha_Return': alpha_val
            })
            
    if not daily_alpha_records:
        return None
        
    df_alpha_all = pd.DataFrame(daily_alpha_records)
    df_pivot = df_alpha_all.pivot(index='Group_Name', columns='Date', values='Alpha_Return').fillna(0.0)
    
    sorted_date_cols = sorted([col for col in df_pivot.columns if col != '7日平均 %'])
    df_pivot = df_pivot[sorted_date_cols]
    
    cumulative_factor = 1.0
    for col in sorted_date_cols:
        cumulative_factor *= (1.0 + df_pivot[col] / 100.0)
    
    df_pivot['7日累積超額 %'] = (cumulative_factor - 1.0) * 100.0
    
    # 根據傳入的是 Sector 還是 Industry，設定正確的 index 名稱
    df_pivot.index.name = '部門板塊' if group_by_col == 'Sector' else '細分行業'
    
    return df_pivot

def main():
    st.title("📊 美股兩日清單動態對比 + 盤前即時監控大盤")
    st.write("---")

    st.markdown("### 📁 數據上傳區")
    st.markdown("💡 **提示：** 正常情況下你**只需要上傳「1️⃣ 最新一日 CSV」** 即可。如果你想查看過往日子，**請勿上傳檔案**，直接使用下方的歷史切換選單。")
    
    col_up1, col_up2 = st.columns(2)
    with col_up1:
        uploaded_new = st.file_uploader("1️⃣ 上傳最新一日 CSV (格式：new_YYYY-MM-DD.csv)", type=["csv"])
    with col_up2:
        uploaded_old = st.file_uploader("2️⃣ [選填] 上傳前一日 CSV (格式：new_YYYY-MM-DD.csv)", type=["csv"])

    df_new, df_old = None, None
    data_source_msg = ""
    active_date_str = datetime.now().strftime("%Y-%m-%d")
    
    local_files = get_all_local_csvs()

    if uploaded_new and uploaded_old:
        df_new = load_and_clean_csv(uploaded_new)
        df_old = load_and_clean_csv(uploaded_old)
        data_source_msg = f"📂 **當前數據來源：** 網頁端手手動上傳兩份 CSV \n* 最新：`{uploaded_new.name}`\n* 前日：`{uploaded_old.name}`"
        m = re.search(r'new_(\d{4}-\d{2}-\d{2})', uploaded_new.name)
        if m: active_date_str = m.group(1)
        trigger_sync(uploaded_new)
        trigger_sync(uploaded_old)

    elif uploaded_new and not uploaded_old:
        df_new = load_and_clean_csv(uploaded_new)
        if local_files:
            target_old_file = local_files[0]
            if os.path.basename(target_old_file) == uploaded_new.name and len(local_files) >= 2:
                target_old_file = local_files[1]
                
            df_old = load_and_clean_csv(target_old_file)
            data_source_msg = f"📂 **當前數據來源：** 智能混合模式\n* 最新（網頁上傳）：`{uploaded_new.name}`\n* 前日（雲端自動匹配）：`{os.path.basename(target_old_file)}`"
        else:
            st.error("❌ 雲端系統內找不到任何歷史數據，請同時上傳前一日的 CSV 進行首度初始化！")
        m = re.search(r'new_(\d{4}-\d{2}-\d{2})', uploaded_new.name)
        if m: active_date_str = m.group(1)
        trigger_sync(uploaded_new)

    elif not uploaded_new and uploaded_old:
        df_old = load_and_clean_csv(uploaded_old)
        if local_files:
            target_new_file = local_files[0]
            if os.path.basename(target_new_file) == uploaded_old.name and len(local_files) >= 2:
                target_new_file = local_files[1]
            df_new = load_and_clean_csv(target_new_file)
            data_source_msg = f"📂 **當前數據來源：** 智能混合模式\n* 最新（雲端自動匹配）：`{os.path.basename(target_new_file)}`\n* 前日（網頁上傳）：`{uploaded_old.name}`"
            m = re.search(r'new_(\d{4}-\d{2}-\d{2})', os.path.basename(target_new_file))
            if m: active_date_str = m.group(1)
        trigger_sync(uploaded_old)

    else:
        st.write("---")
        st.markdown("### 📜 歷史數據快速切換")
        
        if len(local_files) >= 2:
            options = []
            file_map = {}
            
            for i, f in enumerate(local_files[:-1]):
                filename = os.path.basename(f)
                date_match = re.search(r'new_(\d{4}-\d{2}-\d{2})', filename)
                date_str = date_match.group(1) if date_match else filename
                
                display_name = f"📅 {date_str}" + (" (最新雲端數據)" if i == 0 else "")
                options.append(display_name)
                file_map[display_name] = (f, local_files[i+1])
                
            selected_option = st.selectbox(
                "請選擇你想查閱的歷史基準日（系統會自動對比其前一天的數據）：", 
                options,
                index=0
            )
            
            chosen_new_file, chosen_old_file = file_map[selected_option]
            df_new = load_and_clean_csv(chosen_new_file)
            df_old = load_and_clean_csv(chosen_old_file)
            data_source_msg = f"🏛️ **當前數據來源：** 查閱歷史存檔 \n* **新一日（基準）：** `{os.path.basename(chosen_new_file)}` \n* **舊一日（對比）：** `{os.path.basename(chosen_old_file)}`"
            m = re.search(r'new_(\d{4}-\d{2}-\d{2})', os.path.basename(chosen_new_file))
            if m: active_date_str = m.group(1)
        elif len(local_files) == 1:
            df_new = load_and_clean_csv(local_files[0])
            st.warning("⚠️ 目前雲端只有一份 CSV，無法進行兩日對比。請在上方上傳更多歷史數據。")
            return
        else:
            st.info("👋 **歡迎使用！請在上方「數據上傳區」投入最新一日的 CSV 檔案。**")
            return

    if df_new is None or df_old is None:
        return

    st.success(data_source_msg)

    # 比對邏輯
    set_new = set(df_new['Symbol'])
    set_old = set(df_old['Symbol'])
    
    added_symbols = list(set_new - set_old)     
    removed_symbols = list(set_old - set_new)   

    df_added_info = df_new[df_new['Symbol'].isin(added_symbols)][['Symbol', 'Description', 'Price', 'Sector', 'Industry']].rename(
        columns={'Sector': '部門板塊', 'Industry': '行業'}
    )
    df_removed_info = df_old[df_old['Symbol'].isin(removed_symbols)][['Symbol', 'Description', 'Price', 'Sector', 'Industry']].rename(
        columns={'Sector': '部門板塊', 'Industry': '行業'}
    )

    common_symbols = list(set_new & set_old)
    df_new_sub = df_new[df_new['Symbol'].isin(common_symbols)][['Symbol', 'Price', 'Description', 'Sector', 'Industry', 'Market capitalization']]
    df_old_sub = df_old[df_old['Symbol'].isin(common_symbols)][['Symbol', 'Price']]
    df_merge = pd.merge(df_new_sub, df_old_sub, on='Symbol', suffixes=('_new', '_old'))
    df_merge['兩日變幅 %'] = ((df_merge['Price_new'] - df_merge['Price_old']) / df_merge['Price_old']) * 100
    df_merge.rename(columns={'Price_new': '最新收盤價 (新)', 'Price_old': '前日收盤價 (舊)', 'Market capitalization': '市值 (USD)', 'Sector': '部門板塊', 'Industry': '行業'}, inplace=True)

    top_10_gainers = df_merge.sort_values(by='兩日變幅 %', ascending=False).head(10)
    top_10_losers = df_merge.sort_values(by='兩日變幅 %', ascending=True).head(10)

    # 採用安全的三引號解決字串斷行引發的 SyntaxError 
    today_str = datetime.now().strftime("%Y-%m-%d")
    txt_content = generate_tradingview_watchlist_content(df_added_info, df_removed_info, top_10_gainers, top_10_losers)
    
    if txt_content:
        st.download_button(
            label="""📥 點擊下載今日 TradingView 分類導入檔 (.txt)""",
            data=txt_content,
            file_name=f"TV_Watchlist_{today_str}.txt",
            mime="text/plain",
            use_container_width=True
        )

    # 介面排版：呈現 新增 / 剔除 股票細節
    col_add, col_rem = st.columns(2)
    with col_add:
        st.success(f"➕ **新增進榜股票 (共 {len(added_symbols)} 隻)**")
        if not df_added_info.empty: st.dataframe(df_added_info, width='stretch', hide_index=True)
        else: st.write("今日無新增股票。")
            
    with col_rem:
        st.error(f"➖ **被剔除/消失股票 (共 {len(removed_symbols)} 隻)**")
        if not df_removed_info.empty: st.dataframe(df_removed_info, width='stretch', hide_index=True)
        else: st.write("今日無消失股票。")

    # ==================== 1️⃣ 🛠️ 近 7 個交易日板塊【數量變動】熱力圖區塊 ====================
    st.write("---")
    st.subheader("🗺️ 近 7 個交易日板塊趨勢熱力圖 (Sector Momentum Heatmap)")
    st.markdown("💡 **提示：** 橫向觀看可追踪特定板塊隨時間的冷熱切換。數字代表當日該板塊股票的**變動數量**，顏色愈深變動愈劇烈（最右邊為最新交易日）。")
    
    df_add_hm, df_rem_hm = calculate_recent_7_days_trends(local_files, df_new, df_old, active_date_str)
    
    col_hm1, col_hm2 = st.columns(2)
    with col_hm1:
        st.markdown("🟢 **各板塊：新增進榜熱度 (資金流入・動能加溫)**")
        if df_add_hm is not None and not df_add_hm.empty:
            date_cols = [c for c in df_add_hm.columns if c != '總計']
            st.dataframe(
                df_add_hm.style.background_gradient(subset=date_cols, cmap='Greens').format(formatter="{:d}", subset=date_cols),
                width='stretch'
            )
        else:
            st.info("暫無足夠歷史數據生成新增趨勢圖。")
            
    with col_hm2:
        st.markdown("🔴 **各板塊：剔除下榜熱度 (資金流出・轉冷訊號)**")
        if df_rem_hm is not None and not df_rem_hm.empty:
            date_cols = [c for c in df_rem_hm.columns if c != '總計']
            st.dataframe(
                df_rem_hm.style.background_gradient(subset=date_cols, cmap='Reds').format(formatter="{:d}", subset=date_cols),
                width='stretch'
            )
        else:
            st.info("暫無足夠歷史數據生成剔除趨勢圖。")

    # ==================== 2️⃣ 🔥 近 7 個交易日板塊【漲跌強度】熱力圖區塊 ====================
    st.write("---")
    st.subheader("📈 近 7 個交易日板塊漲跌幅強度熱力圖 (Sector Performance Heatmap)")
    st.markdown("💡 **提示：** 本面板計算過去 7 個交易日各板塊平均回報『扣除當日 S&P 500 (SPY) 回報』後的**累積超額複利收益 % (Alpha)**。🟢 **深綠色代表大幅跑贏大盤**，🔴 **深紅色代表大幅跑輸大盤**，中間依 0% 自動平衡。")
    
    with st.spinner('🔄 正在從 yfinance 獲取標普 500 基準並重構板塊複利熱力圖...'):
        df_perf_hm = calculate_recent_7_days_performance(local_files, df_new, df_old, active_date_str, group_by_col='Sector')
    
    if df_perf_hm is not None and not df_perf_hm.empty:
        col_perf1, col_perf2 = st.columns(2)
        date_cols_perf = [c for c in df_perf_hm.columns if c != '7日累積超額 %']
        
        # 安全計算全局極值，避免變數順序與多版本相容性 Bug
        if date_cols_perf:
            vals = df_perf_hm[date_cols_perf].to_numpy()
            max_val = float(max(abs(vals.min()), abs(vals.max())))
            if max_val == 0: max_val = 1.0
        else:
            max_val = 1.0

        # 全體按累積表現排序
        df_all_sorted = df_perf_hm.sort_values(by='7日累積超額 %', ascending=False)

        with col_perf1:
            st.markdown("🏆 **多頭領漲板塊排行 (依 7日累積超額 由強到弱排序)**")
            df_perf_g = df_all_sorted.head(10)
            st.dataframe(
                df_perf_g.style.background_gradient(subset=date_cols_perf, cmap='RdYlGn', vmin=-max_val, vmax=max_val).format(formatter="{:+.2f}%", subset=date_cols_perf + ['7日累積超額 %']),
                width='stretch'
            )
            
        with col_perf2:
            st.markdown("🩸 **空頭領跌板塊排行 (依 7日累積超額 由弱到強排序)**")
            df_perf_l = df_all_sorted.tail(10).sort_values(by='7日累積超額 %', ascending=True)
            st.dataframe(
                df_perf_l.style.background_gradient(subset=date_cols_perf, cmap='RdYlGn', vmin=-max_val, vmax=max_val).format(formatter="{:+.2f}%", subset=date_cols_perf + ['7日累積超額 %']),
                width='stretch'
            )
    else:
        st.info("暫無足夠歷史數據生成漲跌幅強度熱力圖。")

    # ==================== 3️⃣ 🎯 近 7 個交易日細分行業【漲跌強度】熱力圖區塊 ====================
    st.write("---")
    st.subheader("🎯 近 7 個交易日細分行業漲跌幅強度熱力圖 (Industry Performance Heatmap)")
    st.markdown("💡 **提示：** 深入追蹤更精細的**行業 (Industry)** 資金動向。算法與板塊完全一致，同樣扣除了 S&P 500 的市場漲跌幅。")
    
    with st.spinner('🔄 正在重構細分行業複利熱力圖...'):
        df_ind_hm = calculate_recent_7_days_performance(local_files, df_new, df_old, active_date_str, group_by_col='Industry')
    
    if df_ind_hm is not None and not df_ind_hm.empty:
        col_ind1, col_ind2 = st.columns(2)
        date_cols_ind = [c for c in df_ind_hm.columns if c != '7日累積超額 %']
        
        if date_cols_ind:
            vals_ind = df_ind_hm[date_cols_ind].to_numpy()
            max_val_ind = float(max(abs(vals_ind.min()), abs(vals_ind.max())))
            if max_val_ind == 0: max_val_ind = 1.0
        else:
            max_val_ind = 1.0

        # 全體按累積表現排序
        df_ind_sorted = df_ind_hm.sort_values(by='7日累積超額 %', ascending=False)

        with col_ind1:
            st.markdown("🚀 **多頭領漲行業排行 Top 15 (依 7日累積超額 由強到弱排序)**")
            df_ind_g = df_ind_sorted.head(15)
            st.dataframe(
                df_ind_g.style.background_gradient(subset=date_cols_ind, cmap='RdYlGn', vmin=-max_val_ind, vmax=max_val_ind).format(formatter="{:+.2f}%", subset=date_cols_ind + ['7日累積超額 %']),
                width='stretch'
            )
            
        with col_ind2:
            st.markdown("💥 **空頭領跌行業排行 Top 15 (依 7日累積超額 由弱到強排序)**")
            df_ind_l = df_ind_sorted.tail(15).sort_values(by='7日累積超額 %', ascending=True)
            st.dataframe(
                df_ind_l.style.background_gradient(subset=date_cols_ind, cmap='RdYlGn', vmin=-max_val_ind, vmax=max_val_ind).format(formatter="{:+.2f}%", subset=date_cols_ind + ['7日累積超額 %']),
                width='stretch'
            )
    else:
        st.info("暫無足夠歷史數據生成細分行業漲跌幅強度熱力圖。")

    # ==================================================================================================

    st.write("---")

    # 聯網爬即時報價
    all_target_syms = list(set(top_10_gainers['Symbol'].tolist() + top_10_losers['Symbol'].tolist()))
    with st.spinner('🔄 正在同步美股聯網，抓取最新盤前/盤後即時報價...'):
        live_quotes = fetch_live_market_data(all_target_syms)
    
    df_merge['即時市況'] = df_merge['Symbol'].map(lambda x: live_quotes[x]['即時市況'] if x in live_quotes else 'CSV歷史')
    df_merge['即時價'] = df_merge['Symbol'].map(lambda x: live_quotes[x]['最新即時價'] if x in live_quotes else None)
    df_merge['即時總變幅 %'] = df_merge['Symbol'].map(lambda x: live_quotes[x]['即時總變幅 %'] if x in live_quotes else None)
    df_merge['即時價'] = df_merge['即時價'].fillna(df_merge['最新收盤價 (新)'])
    df_merge['即時總變幅 %'] = df_merge['即時總變幅 %'].fillna(df_merge['兩日變幅 %'])

    top_10_gainers_live = df_merge.sort_values(by='兩日變幅 %', ascending=False).head(10)
    top_10_losers_live = df_merge.sort_values(by='兩日變幅 %', ascending=True).head(10)

    cols_to_show = ['Symbol', 'Description', '即時市況', '即時總變幅 %', '即時價', '兩日變幅 %', '最新收盤價 (新)', '前日收盤價 (舊)', '部門板塊', '行業', '市值 (USD)']

    st.subheader("🔥 兩日最強動能排行榜 (Top 10 Gainers) — 支援盤前即時聯網")
    st.dataframe(
        top_10_gainers_live[cols_to_show].style.format({
            '兩日變幅 %': '{:+.2f}%', '最新收盤價 (新)': '${:.2f}', '前日收盤價 (舊)': '${:.2f}', '市值 (USD)': '{:,.0f}',
            '即時總變幅 %': '{:+.2f}%', '即時價': '${:.2f}'
        }).background_gradient(subset=['即時總變幅 %'], cmap='Greens'), width='stretch', hide_index=True
    )

    st.write(" ")
    st.subheader("🩸 兩日失速暴跌排行榜 (Top 10 Losers) — 支援盤前即時聯網")
    st.dataframe(
        top_10_losers_live[cols_to_show].style.format({
            '兩日變幅 %': '{:+.2f}%', '最新收盤價 (新)': '${:.2f}', '前日收盤價 (舊)': '${:.2f}', '市值 (USD)': '{:,.0f}',
            '即時總變幅 %': '{:+.2f}%', '即時價': '${:.2f}'
        }).background_gradient(subset=['即時總變幅 %'], cmap='Reds'), width='stretch', hide_index=True
    )

if __name__ == "__main__":
    main()
