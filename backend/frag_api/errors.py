class RequestContractError(Exception):
    def __init__(self, issues: list[dict[str, str]]):
        self.issues = issues


class RagIndexNotReadyError(Exception): pass
class RagIndexStaleError(Exception): pass
class RagIndexBuildError(Exception): pass
class RagFingerprintError(Exception): pass
class RagNotReadyError(Exception): pass
class RagProviderError(Exception): pass
class RagOutputError(Exception): pass
class HarnessSourceError(Exception): pass
class PluginValidationError(Exception): pass
