"""장보기 알림메모 | 실행: streamlit run app.py
GitHub에 app.py, requirements.txt 업로드 → Streamlit Community Cloud 배포.
영구 보관 필요 시 GROCERY_DB_PATH를 영구 디스크 경로로 지정하세요.
QR은 배포한 앱 URL을 입력해야 다른 휴대폰에서도 열립니다.
"""
import os
import sqlite3
import uuid
from io import BytesIO
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
import streamlit as st
import qrcode

st.set_page_config(page_title="장보기 알림메모", page_icon="🛒", layout="centered", initial_sidebar_state="collapsed")
st.markdown('''<style>
.block-container {max-width:480px;padding:0.65rem 0.8rem 1rem!important;}
header[data-testid="stHeader"] {height:0;background:transparent;}
[data-testid="stToolbar"] {display:none;}
[data-testid="stVerticalBlock"] {gap:.42rem;}
h1 {font-size:1.4rem!important;padding:0!important;}
p {margin-bottom:.2rem;} [data-testid="stMetricValue"] {font-size:1.55rem;}
[data-testid="stCaptionContainer"] p {font-size:.77rem;}
.stButton button {min-height:2.25rem;} [data-testid="stPopover"] button {min-height:2.25rem;}
</style>''', unsafe_allow_html=True)

CATEGORIES=['🥬 야채','🍎 과일','🥩 고기·생선','🥚 유제품·달걀','🍚 쌀·면·빵','🧂 양념·식품','🥤 음료·간식','🧻 생활용품','📦 기타']
PRIORITIES={1:'1 · 꼭 필요',2:'2 · 가격 보고 구매',3:'3 · 비싸면 보류'}
DB=os.environ.get('GROCERY_DB_PATH','grocery.sqlite3')
def connection():
    con=sqlite3.connect(DB,timeout=20)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA busy_timeout=20000')
    return con
with connection() as con:
    con.execute('''CREATE TABLE IF NOT EXISTS items (
        id TEXT PRIMARY KEY, board TEXT NOT NULL, category TEXT NOT NULL,
        name TEXT NOT NULL, priority INTEGER NOT NULL CHECK(priority BETWEEN 1 AND 3),
        target INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending',
        price INTEGER NOT NULL DEFAULT 0, qty REAL NOT NULL DEFAULT 0,
        subtotal INTEGER NOT NULL DEFAULT 0, created TEXT DEFAULT CURRENT_TIMESTAMP)''')

raw=st.query_params.get('list','')
try:
    board=str(uuid.UUID(raw))
except (ValueError,TypeError,AttributeError):
    board=str(uuid.uuid4()); st.query_params['list']=board

def rows():
    with connection() as con:
        return [dict(r) for r in con.execute('SELECT * FROM items WHERE board=? ORDER BY priority, created, id',(board,)).fetchall()]
def mutate(sql,args):
    with connection() as con:
        cur=con.execute(sql,args)
        return cur.rowcount

def money(n): return f'{n:,.0f}원'
def rerun(message):
    st.session_state['notice']=message
    st.rerun()
def subtotal(price,qty):
    return int((Decimal(str(price))*Decimal(str(qty))).quantize(Decimal('1'),rounding=ROUND_HALF_UP))

items=rows(); pending=[x for x in items if x['status']=='pending']; cart=[x for x in items if x['status']=='cart']
st.title('🛒 장보기 알림메모')
a,b=st.columns([3,1])
a.caption('필요한 것만 사고, 담은 금액은 바로 확인')
with b:
    with st.popover('QR 🔗',use_container_width=True):
        st.caption('같은 목록을 열거나 공유합니다. 링크를 가진 사람은 목록을 수정할 수 있어요.')
        base=st.text_input('배포한 앱 주소',placeholder='https://your-app.streamlit.app',key='base_url')
        if base:
            parsed=urlsplit(base.strip())
            if parsed.scheme=='https' and parsed.netloc:
                query=dict(parse_qsl(parsed.query)); query['list']=board
                link=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode(query),''))
                buf=BytesIO(); qrcode.make(link).save(buf,format='PNG')
                st.image(buf.getvalue(),width=190)
                st.code(link,language=None)
            else: st.warning('https://로 시작하는 배포 주소를 입력해 주세요.')
        st.caption('현재 주소를 북마크하면 다시 같은 목록으로 돌아옵니다. QR은 별도 로그인 없이 열립니다.')

left,right=st.columns(2)
left.metric('현재 카트 총액',money(sum(x['subtotal'] for x in cart)))
right.metric('장보기 현황',f'{len(cart)}개 담음',f'{len(pending)}개 남음',delta_color='off')

with st.popover('＋ 살 물건 추가',use_container_width=True):
    with st.form('add',clear_on_submit=True):
        name=st.text_input('상품명',max_chars=60,placeholder='예: 방울토마토 500g')
        category=st.selectbox('카테고리',CATEGORIES)
        priority=st.selectbox('중요도',[1,2,3],format_func=lambda p:PRIORITIES[p],index=1)
        target=st.number_input('희망 최대 단가 (원, 0은 미설정)',min_value=0,max_value=100000000,step=100,value=0)
        st.caption('단가는 한 개·한 팩·1kg 등, 구매 때 입력할 수량 단위에 맞춰 주세요.')
        if st.form_submit_button('메모에 추가',type='primary',use_container_width=True):
            if not name.strip(): st.error('상품명을 입력해 주세요.')
            else:
                mutate('INSERT INTO items(id,board,category,name,priority,target) VALUES(?,?,?,?,?,?)',(str(uuid.uuid4()),board,category,name.strip(),priority,target))
                rerun('메모에 추가했어요.')

st.markdown('**📝 살 물건**')
if pending:
    lookup={x['id']:x for x in pending}
    def label(k):
        x=lookup[k]
        return f"{x['priority']}순위 · {x['category']} · {x['name']}"
    selected=st.selectbox('살 물건 선택',list(lookup),format_func=label,label_visibility='collapsed',key='pending_selection')
    item=lookup[selected]
    target_text=money(item['target']) if item['target'] else '미설정'
    st.caption(f"{PRIORITIES[item['priority']]}  |  희망 최대 단가 {target_text}")
    if item['priority']==1:
        st.caption('🔴 꼭 필요한 품목 · 가격이 부담되면 보류해도 메모는 유지됩니다.')
    else:
        st.caption('🟢 비싸면 아래 ‘보류’ — 사지 않아도 괜찮아요.')
    c1,c2,c3=st.columns([2,1,1])
    with c1:
        with st.popover('🛒 담기',use_container_width=True):
            st.markdown(f"**{item['name']}**")
            # 폼 밖 입력으로 단가·수량 변경 시 예상 금액과 초과 경고를 즉시 갱신합니다.
            price=st.number_input('실제 단가 (원)',min_value=0,max_value=100000000,value=None,step=100,placeholder='가격 입력 필수',key=f'price_{selected}')
            qty=st.number_input('수량 (개·팩·kg 등)',min_value=0.01,max_value=100000.0,value=None,step=1.0,placeholder='수량 입력 필수',key=f'qty_{selected}')
            if price is not None and qty is not None:
                st.info(f'이번에 담을 금액: {money(subtotal(price,qty))}')
                if item['target'] and price>item['target']:
                    st.warning(f"희망 단가보다 {money(price-item['target'])} 비싸요. 구매하지 않고 닫아도 메모가 남습니다.")
                elif item['priority']>=2:
                    st.caption('가격이 부담되면 창을 닫고 보류하세요.')
            if st.button('가격·수량 확인 후 담기',type='primary',use_container_width=True,key=f'buy_{selected}'):
                if price is None or qty is None: st.error('실제 단가와 수량을 모두 입력해 주세요.')
                else:
                    changed=mutate("UPDATE items SET status='cart',price=?,qty=?,subtotal=? WHERE id=? AND board=? AND status='pending'",(price,qty,subtotal(price,qty),selected,board))
                    rerun('카트에 담았어요.' if changed else '다른 기기에서 변경된 목록을 새로 불러왔어요.')
    with c2:
        if st.button('보류',use_container_width=True):
            rerun('보류했어요. 물건은 메모에 그대로 남아 있어요.')
    with c3:
        with st.popover('삭제',use_container_width=True):
            st.caption('구매하지 않을 메모만 삭제하세요. 구매했다면 ‘담기’를 이용하세요.')
            if st.button('메모 삭제 확인',key=f'delete_{selected}',use_container_width=True):
                mutate("DELETE FROM items WHERE id=? AND board=? AND status='pending'",(selected,board)); rerun('메모를 삭제했어요.')
else:
    st.caption('살 물건이 없어요. 위에서 추가해 주세요.')

st.markdown('**🧺 카트 내역**')
if cart:
    cart_lookup={x['id']:x for x in cart}
    picked=st.selectbox('담은 물건 선택',list(cart_lookup),format_func=lambda k:f"{cart_lookup[k]['name']} · {cart_lookup[k]['qty']:g} × {money(cart_lookup[k]['price'])} = {money(cart_lookup[k]['subtotal'])}",label_visibility='collapsed',key='cart_selection')
    with st.popover('금액 수정 / 담기 취소',use_container_width=True):
        x=cart_lookup[picked]
        with st.form(f'edit_{picked}'):
            new_price=st.number_input('수정 단가 (원)',min_value=0,max_value=100000000,value=x['price'],step=100)
            new_qty=st.number_input('수정 수량',min_value=.01,max_value=100000.0,value=float(x['qty']),step=1.0)
            if st.form_submit_button('금액 수정',use_container_width=True):
                mutate("UPDATE items SET price=?,qty=?,subtotal=? WHERE id=? AND board=? AND status='cart'",(new_price,new_qty,subtotal(new_price,new_qty),picked,board)); rerun('카트 금액을 수정했어요.')
        if st.button('담기 취소 → 메모로 되돌리기',use_container_width=True):
            mutate("UPDATE items SET status='pending',price=0,qty=0,subtotal=0 WHERE id=? AND board=? AND status='cart'",(picked,board)); rerun('메모로 되돌렸어요. 총액에서도 제외했어요.')
else:
    st.caption('아직 담은 물건이 없어요.')

footer1,footer2=st.columns(2)
with footer1:
    if st.button('↻ 새로고침',use_container_width=True): st.rerun()
with footer2:
    with st.popover('장보기 마치기',use_container_width=True):
        st.caption('카트 기록을 CSV로 내려받을 수 있어요. 남은 메모는 유지됩니다.')
        import csv
        from io import StringIO
        output=StringIO(); writer=csv.writer(output)
        writer.writerow(['상품명','카테고리','중요도','실제 단가(원)','수량','합계(원)'])
        # 스프레드시트에서 상품명이 수식으로 실행되지 않도록 방어합니다.
        def safe_cell(text): return "'"+text if text.startswith(('=','+','-','@','\t','\r')) else text
        for x in cart: writer.writerow([safe_cell(x['name']),x['category'],x['priority'],x['price'],x['qty'],x['subtotal']])
        writer.writerow(['총액','','','','',sum(x['subtotal'] for x in cart)])
        st.download_button('구매 기록 CSV',output.getvalue().encode('utf-8-sig'),file_name='grocery_cart.csv',mime='text/csv',use_container_width=True)
        confirm=st.checkbox('구매 기록을 저장했으며 카트를 비웁니다')
        if st.button('카트 비우기',disabled=not confirm,use_container_width=True):
            mutate("DELETE FROM items WHERE board=? AND status='cart'",(board,)); rerun('카트를 비웠어요. 남은 메모는 유지됩니다.')

st.caption('QR·주소를 보관하세요 · 공유 중에는 ↻로 최신 상태 확인')
if 'notice' in st.session_state:
    st.toast(st.session_state.pop('notice'))