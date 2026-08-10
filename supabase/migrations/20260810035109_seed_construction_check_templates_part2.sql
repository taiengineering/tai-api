-- 건설 공정별 점검항목 시딩 2/2 — 골조·마감·설비 (13건)
-- 1/2(가설·토공 9건)는 20260810034850_seed_construction_check_templates.sql 참조.
--
-- ⚠️ 원어민 검수 전이다. "거푸집 동바리", "철근 피복" 등 전문 용어가 포함되어 있다.

INSERT INTO construction_check_templates
  (process_key, item_seq, item_code, name_i18n, desc_i18n, risk_i18n)
VALUES
-- ══ 골조공사 (struct) ══
('struct', 1, 'k1',
 '{"ko":"거푸집 동바리 설치·고정 상태","en":"Formwork shoring installation and fixation","zh":"模板支撑安装·固定状态","vi":"Lắp và cố định cây chống cốp pha","ne":"फर्मवर्क सपोर्ट जडान र बलियो अवस्था","km":"ការដំឡើង និងជួសជុលទ្រនាប់ផ្សិត","tl":"Pag-install at pagkakabit ng formwork shoring"}',
 '{"ko":"동바리 수직도, 하중 지지 여부 확인","en":"Check shoring verticality and load bearing","zh":"确认支撑垂直度、承载能力","vi":"Kiểm tra độ thẳng đứng và khả năng chịu tải","ne":"सपोर्ट ठाडोपन र भार बोक्ने क्षमता जाँच","km":"ពិនិត្យភាពត្រង់ និងសមត្ថភាពទ្រទ្រង់ទម្ងន់","tl":"Suriin ang verticality at load bearing"}',
 '{"ko":"붕괴","en":"Collapse","zh":"倒塌","vi":"Sập đổ","ne":"भत्किने","km":"ការបាក់រលំ","tl":"Pagguho"}'),

('struct', 2, 'k2',
 '{"ko":"철근 조립 상태 및 피복 두께","en":"Rebar assembly and cover thickness","zh":"钢筋组装状态及保护层厚度","vi":"Lắp cốt thép và chiều dày lớp bảo vệ","ne":"रिबार जडान र कभर मोटाई","km":"ការតម្លើងដែក និងកម្រាស់ស្រោមបេតុង","tl":"Rebar assembly at kapal ng cover"}',
 '{"ko":"철근 이음, 배치 간격 확인","en":"Check rebar splicing and spacing","zh":"确认钢筋接头、布置间距","vi":"Kiểm tra nối và khoảng cách cốt thép","ne":"रिबार जोड र दूरी जाँच","km":"ពិនិត្យការតភ្ជាប់ និងចន្លោះដែក","tl":"Suriin ang splice at spacing ng rebar"}',
 '{"ko":"구조","en":"Structural","zh":"结构","vi":"Kết cấu","ne":"संरचनात्मक","km":"រចនាសម្ព័ន្ធ","tl":"Istruktural"}'),

('struct', 3, 'k3',
 '{"ko":"콘크리트 타설 전 거푸집 청소","en":"Formwork cleaning before concrete pouring","zh":"混凝土浇筑前模板清扫","vi":"Vệ sinh cốp pha trước khi đổ bê tông","ne":"कंक्रिट हाल्नु अघि फर्मवर्क सफाइ","km":"សម្អាតផ្សិតមុនចាក់បេតុង","tl":"Paglilinis ng formwork bago magbuhos ng kongkreto"}',
 '{"ko":"잡물, 물 제거 여부 확인","en":"Confirm debris and water removal","zh":"确认杂物、积水清除","vi":"Xác nhận đã loại bỏ rác và nước","ne":"फोहोर र पानी हटाइएको जाँच","km":"បញ្ជាក់ការយកសំរាម និងទឹកចេញ","tl":"Kumpirmahin ang pagtanggal ng debris at tubig"}',
 '{"ko":"품질","en":"Quality","zh":"质量","vi":"Chất lượng","ne":"गुणस्तर","km":"គុណភាព","tl":"Kalidad"}'),

('struct', 4, 'k4',
 '{"ko":"고소 작업 시 안전벨트 착용","en":"Safety harness use during work at height","zh":"高处作业时佩戴安全带","vi":"Đeo dây an toàn khi làm việc trên cao","ne":"उचाइमा काम गर्दा सेफ्टी बेल्ट लगाउने","km":"ពាក់ខ្សែក្រវាត់សុវត្ថិភាពពេលធ្វើការលើកម្ពស់","tl":"Paggamit ng safety harness sa trabaho sa taas"}',
 '{"ko":"슬라브 단부·개구부 추락 방지 확인","en":"Check fall protection at slab edges and openings","zh":"确认楼板边缘·开口坠落防护","vi":"Kiểm tra chống ngã tại mép sàn và lỗ mở","ne":"स्ल्याब किनारा र प्वालमा खस्ने रोकथाम जाँच","km":"ពិនិត្យការការពារធ្លាក់នៅគែម និងរន្ធ","tl":"Suriin ang fall protection sa gilid at butas ng slab"}',
 '{"ko":"추락","en":"Fall","zh":"坠落","vi":"Ngã cao","ne":"खस्ने","km":"ការធ្លាក់","tl":"Pagkahulog"}'),

('struct', 5, 'k5',
 '{"ko":"크레인 인양 신호수 배치","en":"Signaler assigned for crane lifting","zh":"起重机吊装信号员配置","vi":"Bố trí người báo hiệu khi cẩu nâng","ne":"क्रेन उठाउँदा संकेतकर्ता तैनाती","km":"ការដាក់អ្នកផ្តល់សញ្ញាពេលលើកដោយក្រេន","tl":"Signaler para sa crane lifting"}',
 '{"ko":"인양 작업 중 신호수 위치 확인","en":"Confirm signaler position during lifting","zh":"确认吊装作业中信号员位置","vi":"Xác nhận vị trí người báo hiệu khi nâng","ne":"उठाउने काममा संकेतकर्ता स्थान जाँच","km":"បញ្ជាក់ទីតាំងអ្នកផ្តល់សញ្ញាពេលលើក","tl":"Kumpirmahin ang posisyon ng signaler"}',
 '{"ko":"충돌","en":"Collision","zh":"碰撞","vi":"Va chạm","ne":"ठक्कर","km":"ការប៉ះទង្គិច","tl":"Banggaan"}'),

-- ══ 마감공사 (finish) ══
('finish', 1, 'm1',
 '{"ko":"내부 비계·발판 안전 상태","en":"Interior scaffold and platform safety","zh":"内部脚手架·踏板安全状态","vi":"An toàn giàn giáo và sàn thao tác trong nhà","ne":"भित्री स्क्याफोल्ड र प्लेटफर्म सुरक्षा","km":"សុវត្ថិភាពរនាំង និងវេទិកាខាងក្នុង","tl":"Kaligtasan ng interior scaffold at platform"}',
 '{"ko":"이동식 비계 고정핀, 발판 과적 확인","en":"Check mobile scaffold locking pins and platform overload","zh":"确认移动脚手架固定销、踏板超载","vi":"Kiểm tra chốt khóa giàn giáo di động và quá tải sàn","ne":"चल स्क्याफोल्ड लक पिन र प्लेटफर्म ओभरलोड जाँच","km":"ពិនិត្យខ្ទាស់ចាក់សោ និងការផ្ទុកលើស","tl":"Suriin ang locking pin at overload ng platform"}',
 '{"ko":"추락","en":"Fall","zh":"坠落","vi":"Ngã cao","ne":"खस्ने","km":"ការធ្លាក់","tl":"Pagkahulog"}'),

('finish', 2, 'm2',
 '{"ko":"도장·도료 환기 조치","en":"Ventilation for painting work","zh":"涂装·涂料通风措施","vi":"Thông gió khi sơn","ne":"पेन्टिङ कार्यमा भेन्टिलेसन","km":"ការបញ្ចេញខ្យល់ពេលលាបថ្នាំ","tl":"Bentilasyon para sa pagpipintura"}',
 '{"ko":"유기용제 취급 시 환기 설비 가동 확인","en":"Confirm ventilation running when handling organic solvents","zh":"确认使用有机溶剂时通风设备运行","vi":"Xác nhận quạt thông gió hoạt động khi dùng dung môi","ne":"अर्गानिक सल्भेन्ट प्रयोगमा भेन्टिलेसन चलेको जाँच","km":"បញ្ជាក់ការដំណើរការឧបករណ៍ខ្យល់ពេលប្រើសារធាតុរំលាយ","tl":"Kumpirmahin ang ventilation kapag may organic solvent"}',
 '{"ko":"화학","en":"Chemical","zh":"化学","vi":"Hóa chất","ne":"रासायनिक","km":"គីមី","tl":"Kemikal"}'),

('finish', 3, 'm3',
 '{"ko":"절단·연마 시 보안경·방진마스크 착용","en":"Goggles and dust mask when cutting or grinding","zh":"切割·打磨时佩戴护目镜·防尘口罩","vi":"Đeo kính và khẩu trang khi cắt, mài","ne":"काट्दा·घोट्दा चश्मा र धुलो मास्क लगाउने","km":"ពាក់វ៉ែនតា និងម៉ាស់ការពារធូលីពេលកាត់ ឬកិន","tl":"Goggles at dust mask sa pagputol o paggiling"}',
 '{"ko":"비산 먼지·파편 차단 보호구 확인","en":"Check PPE against flying dust and fragments","zh":"确认防护飞散粉尘·碎片的护具","vi":"Kiểm tra bảo hộ chống bụi và mảnh văng","ne":"उड्ने धुलो र टुक्रा रोक्ने सुरक्षा उपकरण जाँच","km":"ពិនិត្យឧបករណ៍ការពារធូលី និងកម្ទេច","tl":"Suriin ang PPE laban sa alikabok at fragment"}',
 '{"ko":"비산","en":"Flying debris","zh":"飞散","vi":"Vật văng","ne":"उड्ने कण","km":"កម្ទេចខ្ចាត់ខ្ចាយ","tl":"Lumilipad na debris"}'),

('finish', 4, 'm4',
 '{"ko":"전동공구 안전 장치 작동 여부","en":"Power tool safety guard operation","zh":"电动工具安全装置运行","vi":"Hoạt động của bộ phận an toàn dụng cụ điện","ne":"पावर टुल सुरक्षा उपकरण काम गरेको","km":"ដំណើរការឧបករណ៍ការពារនៃឧបករណ៍អគ្គិសនី","tl":"Paggana ng safety guard ng power tool"}',
 '{"ko":"그라인더, 드릴 등 방호 덮개 확인","en":"Check protective covers on grinders and drills","zh":"确认砂轮机、电钻等防护罩","vi":"Kiểm tra nắp bảo vệ máy mài, khoan","ne":"ग्राइन्डर, ड्रिल सुरक्षा कभर जाँच","km":"ពិនិត្យគម្របការពារម៉ាស៊ីនកិន និងស្វាន","tl":"Suriin ang protective cover ng grinder at drill"}',
 '{"ko":"협착","en":"Entanglement","zh":"夹伤","vi":"Kẹp cuốn","ne":"च्यापिने","km":"ការកិនច្របាច់","tl":"Pagkakaipit"}'),

-- ══ 설비공사 (mep) ══
('mep', 1, 's1',
 '{"ko":"배관 지지·고정 상태","en":"Pipe support and fixation","zh":"管道支撑·固定状态","vi":"Đỡ và cố định đường ống","ne":"पाइप सपोर्ट र बलियो अवस्था","km":"ការទ្រទ្រង់ និងជួសជុលបំពង់","tl":"Suporta at pagkakabit ng tubo"}',
 '{"ko":"행어, 서포트 체결 및 간격 확인","en":"Check hanger and support fastening and spacing","zh":"确认吊架、支架紧固及间距","vi":"Kiểm tra siết và khoảng cách giá đỡ","ne":"ह्याङ्गर, सपोर्ट कस्ने र दूरी जाँच","km":"ពិនិត្យការរឹតបន្តឹង និងចន្លោះទ្រនាប់","tl":"Suriin ang hanger at support spacing"}',
 '{"ko":"낙하","en":"Falling object","zh":"坠落物","vi":"Vật rơi","ne":"खस्ने वस्तु","km":"វត្ថុធ្លាក់","tl":"Nahuhulog na bagay"}'),

('mep', 2, 's2',
 '{"ko":"전기 배관 절연 및 접지","en":"Electrical conduit insulation and grounding","zh":"电气配管绝缘及接地","vi":"Cách điện và tiếp địa ống điện","ne":"विद्युत पाइप इन्सुलेसन र अर्थिङ","km":"អ៊ីសូឡង់ និងដីនៃបំពង់អគ្គិសនី","tl":"Insulation at grounding ng electrical conduit"}',
 '{"ko":"케이블 덕트, 트레이 접지 연속성 확인","en":"Check grounding continuity of cable ducts and trays","zh":"确认电缆管道、桥架接地连续性","vi":"Kiểm tra liên tục tiếp địa máng cáp","ne":"केबल डक्ट, ट्रे अर्थिङ निरन्तरता जाँच","km":"ពិនិត្យភាពបន្តនៃដីខ្សែ","tl":"Suriin ang grounding continuity ng cable tray"}',
 '{"ko":"감전","en":"Electric shock","zh":"触电","vi":"Điện giật","ne":"करेन्ट लाग्ने","km":"ការឆក់អគ្គិសនី","tl":"Kuryente"}'),

('mep', 3, 's3',
 '{"ko":"소방 배관 압력 테스트 여부","en":"Fire piping pressure test","zh":"消防管道压力测试","vi":"Thử áp lực đường ống PCCC","ne":"अग्नि पाइप प्रेसर परीक्षण","km":"ការសាកល្បងសម្ពាធបំពង់ពន្លត់អគ្គីភ័យ","tl":"Pressure test ng fire piping"}',
 '{"ko":"수압 시험 완료 여부 확인","en":"Confirm hydrostatic test completion","zh":"确认水压试验完成","vi":"Xác nhận hoàn thành thử thủy lực","ne":"जलदाब परीक्षण सम्पन्न जाँच","km":"បញ្ជាក់ការបញ្ចប់សាកល្បងសម្ពាធទឹក","tl":"Kumpirmahin ang hydrostatic test"}',
 '{"ko":"누수","en":"Leakage","zh":"漏水","vi":"Rò rỉ","ne":"चुहावट","km":"ការលេចធ្លាយ","tl":"Tagas"}'),

('mep', 4, 's4',
 '{"ko":"용접·화기 작업 전 소화기 배치","en":"Fire extinguisher placement before hot work","zh":"焊接·动火作业前配置灭火器","vi":"Bố trí bình chữa cháy trước khi hàn","ne":"वेल्डिङ·आगो काम अघि अग्नि निभाउने यन्त्र राख्ने","km":"ដាក់ធុងពន្លត់អគ្គីភ័យមុនការងារផ្សារ","tl":"Fire extinguisher bago ang hot work"}',
 '{"ko":"화기 작업 반경 5m 이내 소화기 준비","en":"Extinguisher ready within 5m of hot work","zh":"动火作业半径5m内准备灭火器","vi":"Bình chữa cháy trong bán kính 5m","ne":"आगो कामको ५ मिटर भित्र अग्नि निभाउने यन्त्र","km":"ធុងពន្លត់ក្នុងចម្ងាយ ៥ ម៉ែត្រ","tl":"Extinguisher sa loob ng 5m ng hot work"}',
 '{"ko":"화재","en":"Fire","zh":"火灾","vi":"Cháy","ne":"आगलागी","km":"អគ្គីភ័យ","tl":"Sunog"}')

ON CONFLICT (process_key, item_code) DO NOTHING;
