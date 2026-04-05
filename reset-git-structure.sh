#!/bin/bash
# macOS TAI Engineering 폴더 구조 원복 및 단일 Git 관리 설정
# 사용: bash ~/TAI/reset-git-structure.sh

set -e  # 에러 발생 시 즉시 중단

echo "🔄 TAI 폴더 구조 원복 시작..."

# 1. 각 폴더의 .git 제거
echo "1️⃣ 각 폴더의 .git 폴더 삭제 중..."
rm -rf ~/TAI/1-planning/.git
rm -rf ~/TAI/2-backend/.git
rm -rf ~/TAI/3-frontend/.git
echo "   ✅ 완료"

# 2. 각 폴더의 설정파일 삭제
echo "2️⃣ 각 폴더의 로컬 설정파일 삭제..."
rm -f ~/TAI/1-planning/.gitignore
rm -f ~/TAI/2-backend/.gitignore
rm -f ~/TAI/3-frontend/.gitignore
rm -f ~/TAI/1-planning/claude-config.json
rm -f ~/TAI/2-backend/claude-config.json
rm -f ~/TAI/3-frontend/claude-config.json
echo "   ✅ 완료"

# 3. 루트 폴더에서 Git 초기화
echo "3️⃣ ~/TAI를 루트로 하는 Git 저장소 생성..."
cd ~/TAI
git init
echo "   ✅ 완료"

# 4. .gitignore 생성
echo "4️⃣ .gitignore 생성..."
cat > ~/.TAI/.gitignore << 'EOF'
# IDE
.vscode/
.idea/
*.swp
*.swo
*~
.DS_Store

# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
env/
venv/
*.egg-info/
dist/
build/

# Node
node_modules/
npm-debug.log

# Environment
.env
.env.local
.env.*.local

# IDE config per window
**/claude-config-local.json

# Logs
*.log
EOF
echo "   ✅ 완료"

# 5. 메인 claude-config.json 생성
echo "5️⃣ 메인 claude-config.json 생성..."
cat > ~/TAI/claude-config.json << 'EOF'
{
  "project": "TAI Engineering",
  "root": "~/TAI/",
  "git_management": "single_repository",
  "windows": {
    "window_1": {
      "name": "TAI Planning (기획/메모리)",
      "path": "~/TAI/1-planning/",
      "mcps": ["github-tai", "supabase-tai"],
      "purpose": "Strategy, Documentation, Session Memory"
    },
    "window_2": {
      "name": "TAI Backend (백엔드 개발)",
      "path": "~/TAI/2-backend/",
      "mcps": ["github-tai", "supabase-tai"],
      "git_repo": "taiengineering/tai-api",
      "purpose": "FastAPI development, Database operations"
    },
    "window_3": {
      "name": "TAI Frontend (프론트엔드 개발)",
      "path": "~/TAI/3-frontend/",
      "mcps": ["github-tai-admin", "supabase-tai"],
      "git_repo": "taiengineering/tai-admin",
      "purpose": "Vue HTML development, UI design"
    }
  },
  "mcps": {
    "github": {
      "github-tai": {
        "repo": "taiengineering/tai-api",
        "branch": "main"
      },
      "github-tai-admin": {
        "repo": "taiengineering/tai-admin",
        "branch": "main"
      }
    },
    "supabase": {
      "supabase-tai": {
        "project_id": "xntdkrjhgcscmqctdzyo",
        "shared": true
      }
    }
  }
}
EOF
echo "   ✅ 완료"

# 6. 초기 커밋
echo "6️⃣ 초기 Git 커밋..."
cd ~/TAI
git add .
git commit -m "feat: TAI Engineering 단일 Git 저장소 초기화"
echo "   ✅ 완료"

# 7. 현재 상태 표시
echo ""
echo "✅ 원복 완료!"
echo ""
echo "📁 현재 구조:"
tree -L 2 -a ~/TAI 2>/dev/null || find ~/TAI -maxdepth 2 -type f | head -20
echo ""
echo "🔗 Git 상태:"
cd ~/TAI && git status
echo ""
echo "📋 다음 단계:"
echo "1. ~/TAI/2-backend/ 폴더로 이동"
echo "   cd ~/TAI/2-backend"
echo ""
echo "2. tai-api 저장소 클론"
echo "   git clone https://github.com/taiengineering/tai-api . --depth=1"
echo ""
echo "3. ~/TAI/3-frontend/ 폴더로 이동"
echo "   cd ~/TAI/3-frontend"
echo ""
echo "4. tai-admin 저장소 클론"
echo "   git clone https://github.com/taiengineering/tai-admin . --depth=1"
echo ""
echo "5. 메인 저장소로 돌아가기"
echo "   cd ~/TAI"
echo "   git add 2-backend/ 3-frontend/"
echo "   git commit -m 'feat: tai-api와 tai-admin 클론 추가'"
