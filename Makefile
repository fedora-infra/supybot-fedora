VERSION = 0.2.14

.PHONY: dist

dist:
	mkdir -p dist
	mkdir -p supybot-fedora-$(VERSION)
	cp *.py *.txt supybot-fedora-$(VERSION)
	tar cj supybot-fedora-$(VERSION) > dist/supybot-fedora-$(VERSION).tar.bz2
	rm -rf supybot-fedora-$(VERSION)

clean:
	rm -rf dist
