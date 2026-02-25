.PHONY: setup backend frontend build-frontend start-backend start-frontend mobile-get mobile-analyze mobile-test mobile-ios-build

setup:
	./scripts/setup_backend.sh
	./scripts/setup_frontend.sh

backend:
	./scripts/run_backend.sh

frontend:
	./scripts/run_frontend.sh

build-frontend:
	./scripts/build_frontend.sh

start-backend:
	./scripts/start_backend_prod.sh

start-frontend:
	./scripts/start_frontend_prod.sh

mobile-get:
	cd mobile && flutter pub get

mobile-analyze:
	cd mobile && flutter analyze

mobile-test:
	cd mobile && flutter test

mobile-ios-build:
	cd mobile && flutter build ios --debug --no-codesign
