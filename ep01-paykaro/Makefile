.PHONY: up down reset logs users bot-off bot-on vendor login chat knock

up:          ## build and start PayKaro plus the FDE's tools (needs LLM_API_KEY in the env or .env for the bot)
	docker compose up -d --build

down:        ## stop everything (the lab is stateless)
	docker compose down

reset: down up

logs:        ## follow the app services
	docker compose logs -f login auth otp-service egress-proxy sms-vendor support-bot

users:       ## what the users are experiencing, every 10s
	docker compose logs -f users

bot-off:     ## "before the bot launched": users wait instead of asking the bot
	BOT_ENABLED=false docker compose up -d users

bot-on:      ## the bot is live again
	BOT_ENABLED=true docker compose up -d users

vendor:      ## the SMS vendor account: quota, accepted, rejected
	@curl -s localhost:8003/account; echo

login:       ## log in once as +919800000001
	@curl -s -X POST localhost:8000/login -H 'content-type: application/json' -d '{"phone":"+919800000001"}'; echo

chat:        ## complain to the bot once as +919800000001
	@curl -s -X POST localhost:8004/chat -H 'content-type: application/json' \
	  -d '{"phone":"+919800000001","messages":[{"role":"user","content":"Hi, I did not get my OTP."}]}'; echo

knock:       ## time one HTTPS send through the bank proxy: connect / TLS handshake / request
	docker compose run --rm --no-deps users python knock.py
