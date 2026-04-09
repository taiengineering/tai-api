function goDash(){
  var t = localStorage.getItem('access_token');
  // 결제 완료 후 법령진단 입력폼으로 이동
  location.href = t
    ? 'https://taieng.co.kr/request/v1/'
    : 'https://api.taieng.co.kr/payments/pricing';
}