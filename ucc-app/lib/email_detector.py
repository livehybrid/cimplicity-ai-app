"""Email detection that does not swallow the key in key=value text.

scrubadub's EmailDetector allows '=' in the local part of an address (it is
legal in RFC 5322), so in Splunk-style key=value text such as
``user=alice@example.com`` it reports ``user=alice@example.com`` as the email.
A mask or SEDCMD built from that span hides the key as well as the address.

This detector runs scrubadub's own regex and then trims each match to the part
after the last '=' in the local part, so the span (beg, end and text) covers
the address only. Trade-off: an address that genuinely contains '=' in its
local part (SRS-rewritten bounce addresses, for example) is reported from its
last '=' onwards, which in log data is far rarer than key=value.
"""
from typing import Generator, Optional

from scrubadub.detectors import EmailDetector
from scrubadub.filth import Filth


class KeyValueEmailDetector(EmailDetector):
    """EmailDetector whose matches never start with a ``key=`` prefix."""

    def iter_filth(self, text: str, document_name: Optional[str] = None) -> Generator[Filth, None, None]:
        for filth in super().iter_filth(text, document_name=document_name):
            at = self.at_matcher.search(filth.text)
            cut = filth.text.rfind('=', 0, at.start()) if at else -1
            if cut < 0:
                yield filth
                continue
            beg = filth.beg + cut + 1
            if beg >= filth.beg + at.start():
                # Nothing left of the local part ("key=@host"): not an address.
                continue
            yield self.filth_cls(
                beg=beg,
                end=filth.end,
                text=text[beg:filth.end],
                detector_name=self.name,
                document_name=document_name,
                locale=self.locale,
            )
