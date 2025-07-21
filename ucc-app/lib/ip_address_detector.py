import re
from scrubadub.detectors.base import Detector
from scrubadub.filth.base import Filth

class IpAddressFilth(Filth):
    type = "ip_address"

class IpAddressDetector(Detector):
    name = "IpAddressDetector"
    filth_cls = IpAddressFilth

    ipv4_regex = re.compile(r"\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b")

    def iter_filth(self, text, document_name=None, **kwargs):
        for match in self.ipv4_regex.finditer(text):
            filth = self.filth_cls(
                beg=match.start(),
                end=match.end(),
                text=match.group(),
                detector_name=self.name
            )
            yield filth 