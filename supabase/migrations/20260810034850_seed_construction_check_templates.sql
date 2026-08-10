-- 건설 공정별 점검항목 시딩 (22건 × 7개 언어)
--
-- 출처: /app/construction_inspect.html 의 PROCESS_DATA 하드코딩분.
-- 한국어 원문은 그대로 옮기고 나머지 6개 언어를 채운다.
--
-- ⚠️ 원어민 검수를 거치지 않았다. "흙막이 지보공", "거푸집 동바리" 등 전문 건설
--    용어가 포함되어 있고, 안전 점검 항목의 오역은 현장 위험으로 이어진다.
--    각 언어 가능자 확인 후 확정할 것. 검수 전에도 한국어보다는 읽히므로 배포한다.
--
-- 재실행 안전: (process_key, item_code) 유니크 제약에 ON CONFLICT DO NOTHING.

INSERT INTO construction_check_templates
  (process_key, item_seq, item_code, name_i18n, desc_i18n, risk_i18n)
VALUES
-- ══ 가설공사 (temp) ══
('temp', 1, 'g1',
 '{"ko":"가설 울타리·방호 시트 설치 상태","en":"Temporary fence and protective sheet installation","zh":"临时围栏·防护布安装状态","vi":"Tình trạng lắp hàng rào tạm và bạt che","ne":"अस्थायी बार र सुरक्षा पर्दा जडान अवस्था","km":"ស្ថានភាពដំឡើងរបងបណ្ដោះអាសន្ន និងសន្លឹកការពារ","tl":"Kalagayan ng pansamantalang bakod at protective sheet"}',
 '{"ko":"공사장 외부 경계 안전시설 확인","en":"Check perimeter safety installations","zh":"确认工地外部边界安全设施","vi":"Kiểm tra thiết bị an toàn ranh giới công trường","ne":"निर्माण स्थल बाहिरी सीमा सुरक्षा संरचना जाँच","km":"ពិនិត្យបរិក្ខារសុវត្ថិភាពព្រំដែនការដ្ឋាន","tl":"Suriin ang safety installation sa gilid ng site"}',
 '{"ko":"충돌·낙하","en":"Collision / Falling object","zh":"碰撞·坠落物","vi":"Va chạm / Vật rơi","ne":"ठक्कर / खस्ने वस्तु","km":"ការប៉ះទង្គិច / វត្ថុធ្លាក់","tl":"Banggaan / Nahuhulog na bagay"}'),

('temp', 2, 'g2',
 '{"ko":"가설 계단·통로 안전 상태","en":"Temporary stairs and walkway safety","zh":"临时楼梯·通道安全状态","vi":"An toàn cầu thang và lối đi tạm","ne":"अस्थायी भर्‍याङ र बाटो सुरक्षा अवस्था","km":"សុវត្ថិភាពជណ្ដើរ និងផ្លូវដើរបណ្ដោះអាសន្ន","tl":"Kaligtasan ng pansamantalang hagdan at daanan"}',
 '{"ko":"발판 고정, 난간 설치 여부 점검","en":"Check footing fixation and handrail installation","zh":"检查踏板固定、护栏安装","vi":"Kiểm tra cố định bậc và lắp lan can","ne":"पाइला बलियो र ह्यान्डरेल जडान जाँच","km":"ពិនិត្យការជួសជុលជណ្ដើរ និងដំឡើងរនាំង","tl":"Suriin ang pagkakabit ng footing at handrail"}',
 '{"ko":"추락","en":"Fall","zh":"坠落","vi":"Ngã cao","ne":"खस्ने","km":"ការធ្លាក់","tl":"Pagkahulog"}'),

('temp', 3, 'g3',
 '{"ko":"가설 전기설비 절연 상태","en":"Temporary electrical equipment insulation","zh":"临时电气设备绝缘状态","vi":"Tình trạng cách điện thiết bị điện tạm","ne":"अस्थायी विद्युत उपकरण इन्सुलेसन अवस्था","km":"ស្ថានភាពអ៊ីសូឡង់ឧបករណ៍អគ្គិសនីបណ្ដោះអាសន្ន","tl":"Insulation ng pansamantalang electrical equipment"}',
 '{"ko":"임시 배전반, 케이블 절연 피복 확인","en":"Check temporary switchboard and cable insulation","zh":"确认临时配电盘、电缆绝缘层","vi":"Kiểm tra tủ điện tạm và vỏ cách điện cáp","ne":"अस्थायी स्विचबोर्ड र केबल इन्सुलेसन जाँच","km":"ពិនិត្យបន្ទះចែកចរន្ត និងស្រោមខ្សែ","tl":"Suriin ang temporary switchboard at cable insulation"}',
 '{"ko":"감전","en":"Electric shock","zh":"触电","vi":"Điện giật","ne":"करेन्ट लाग्ने","km":"ការឆក់អគ្គិសនី","tl":"Kuryente"}'),

('temp', 4, 'g4',
 '{"ko":"비계 설치 및 고정 상태","en":"Scaffolding installation and fixation","zh":"脚手架安装及固定状态","vi":"Lắp đặt và cố định giàn giáo","ne":"स्क्याफोल्डिङ जडान र बलियो अवस्था","km":"ការដំឡើង និងជួសជុលរនាំងសំណង់","tl":"Pag-install at pagkakabit ng scaffolding"}',
 '{"ko":"비계 수직도, 브래킷 체결 여부 확인","en":"Check scaffold verticality and bracket fastening","zh":"确认脚手架垂直度、支架紧固","vi":"Kiểm tra độ thẳng đứng và siết bracket","ne":"स्क्याफोल्ड ठाडोपन र ब्राकेट कस्ने जाँच","km":"ពិនិត្យភាពត្រង់ និងការរឹតបន្តឹងតង្កៀប","tl":"Suriin ang verticality at pagkakahigpit ng bracket"}',
 '{"ko":"붕괴","en":"Collapse","zh":"倒塌","vi":"Sập đổ","ne":"भत्किने","km":"ការបាក់រលំ","tl":"Pagguho"}'),

-- ══ 토공사 (earth) ══
('earth', 1, 't1',
 '{"ko":"굴착면 기울기·경사 안전 상태","en":"Excavation slope safety","zh":"开挖面坡度安全状态","vi":"An toàn độ dốc mặt đào","ne":"उत्खनन सतह ढलान सुरक्षा अवस्था","km":"សុវត្ថិភាពជម្រាលផ្ទៃជីក","tl":"Kaligtasan ng slope ng hukay"}',
 '{"ko":"토사 붕괴 위험 여부 확인","en":"Check risk of soil collapse","zh":"确认土砂坍塌危险","vi":"Kiểm tra nguy cơ sạt lở đất","ne":"माटो भत्किने जोखिम जाँच","km":"ពិនិត្យហានិភ័យបាក់ដី","tl":"Suriin ang panganib ng pagguho ng lupa"}',
 '{"ko":"붕괴","en":"Collapse","zh":"倒塌","vi":"Sập đổ","ne":"भत्किने","km":"ការបាក់រលំ","tl":"Pagguho"}'),

('earth', 2, 't2',
 '{"ko":"흙막이 지보공 설치 상태","en":"Earth retaining support installation","zh":"挡土支撑安装状态","vi":"Lắp đặt chống đỡ chắn đất","ne":"माटो रोक्ने सपोर्ट जडान अवस्था","km":"ការដំឡើងទ្រនាប់ការពារដី","tl":"Pag-install ng earth retaining support"}',
 '{"ko":"H파일, 토류판 설치 및 고정 확인","en":"Check H-pile and lagging installation and fixation","zh":"确认H型钢桩、挡土板安装及固定","vi":"Kiểm tra lắp và cố định cọc H, tấm chắn đất","ne":"H-पाइल र माटो प्यानल जडान जाँच","km":"ពិនិត្យការដំឡើងសសរ H និងបន្ទះការពារដី","tl":"Suriin ang H-pile at lagging"}',
 '{"ko":"붕괴","en":"Collapse","zh":"倒塌","vi":"Sập đổ","ne":"भत्किने","km":"ការបាក់រលំ","tl":"Pagguho"}'),

('earth', 3, 't3',
 '{"ko":"굴착 주변 지상 균열·침하 여부","en":"Ground cracks and subsidence near excavation","zh":"开挖周边地面裂缝·沉降","vi":"Nứt và lún nền quanh hố đào","ne":"उत्खनन वरिपरि जमिन चर्किने र धस्ने","km":"ស្នាមប្រេះ និងការស្រុតដីជុំវិញកន្លែងជីក","tl":"Bitak at paglubog ng lupa malapit sa hukay"}',
 '{"ko":"굴착 주변 지반 상태 육안 점검","en":"Visual check of ground condition around excavation","zh":"目视检查开挖周边地基状态","vi":"Kiểm tra bằng mắt nền đất quanh hố đào","ne":"उत्खनन वरिपरि जमिन अवस्था आँखाले जाँच","km":"ពិនិត្យដោយភ្នែកនូវស្ថានភាពដីជុំវិញ","tl":"Visual na pagsuri sa lupa sa paligid"}',
 '{"ko":"붕괴","en":"Collapse","zh":"倒塌","vi":"Sập đổ","ne":"भत्किने","km":"ការបាក់រលំ","tl":"Pagguho"}'),

('earth', 4, 't4',
 '{"ko":"중장비 작업 반경 내 출입 통제","en":"Access control within heavy equipment radius","zh":"重型设备作业半径内出入管制","vi":"Kiểm soát ra vào trong bán kính máy nặng","ne":"भारी उपकरण कार्य क्षेत्रमा प्रवेश नियन्त्रण","km":"ការគ្រប់គ្រងចូលក្នុងតំបន់ម៉ាស៊ីនធុនធ្ងន់","tl":"Access control sa radius ng heavy equipment"}',
 '{"ko":"굴착기·덤프 작업 구역 접근 차단 확인","en":"Confirm access is blocked around excavator and dump truck","zh":"确认挖掘机·自卸车作业区域禁入","vi":"Xác nhận chặn tiếp cận khu máy xúc, xe ben","ne":"एक्साभेटर·डम्प कार्य क्षेत्र पहुँच रोक जाँच","km":"បញ្ជាក់ការហាមចូលតំបន់ម៉ាស៊ីនជីក និងឡានដឹក","tl":"Kumpirmahin ang pagharang sa excavator at dump area"}',
 '{"ko":"충돌","en":"Collision","zh":"碰撞","vi":"Va chạm","ne":"ठक्कर","km":"ការប៉ះទង្គិច","tl":"Banggaan"}'),

('earth', 5, 't5',
 '{"ko":"낙하물 방지망 설치 상태","en":"Falling object protection net installation","zh":"落物防护网安装状态","vi":"Lắp lưới chống vật rơi","ne":"खस्ने वस्तु रोक्ने जाली जडान अवस्था","km":"ការដំឡើងសំណាញ់ការពារវត្ថុធ្លាក់","tl":"Pag-install ng falling object protection net"}',
 '{"ko":"굴착부 상부 낙하 위험물 방지 조치","en":"Measures against falling objects above excavation","zh":"开挖部上方落物危险防护措施","vi":"Biện pháp chống vật rơi phía trên hố đào","ne":"उत्खनन माथिबाट खस्ने जोखिम रोक्ने उपाय","km":"វិធានការការពារវត្ថុធ្លាក់ពីលើកន្លែងជីក","tl":"Panangga sa nahuhulog na bagay sa itaas ng hukay"}',
 '{"ko":"낙하","en":"Falling object","zh":"坠落物","vi":"Vật rơi","ne":"खस्ने वस्तु","km":"វត្ថុធ្លាក់","tl":"Nahuhulog na bagay"}')

ON CONFLICT (process_key, item_code) DO NOTHING;
