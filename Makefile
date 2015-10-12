VERSION = 0.3.5

.PHONY: dist

dist:
	mkdir -p dist
	mkdir -p supybot-fedora-$(VERSION)
	cp *.py *.txt supybot-fedora-$(VERSION)
	tar cj supybot-fedora-$(VERSION) > dist/supybot-fedora-$(VERSION).tar.bz2
	rm -rf supybot-fedora-$(VERSION)

upload:
	scp dist/supybot-fedora-$(VERSION).tar.bz2 $(BODHI_USER)@fedorahosted.org:/srv/web/releases/s/u/supybot-fedora/.

clean:
	rm -rf dist
