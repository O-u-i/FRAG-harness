class RagIndexNotReadyError(Exception): pass
class RagIndexStaleError(Exception): pass
class RagIndexBuildError(Exception): pass
class PluginValidationError(Exception): pass
class PolicyRejectedError(Exception): pass
class RuntimeNotFoundError(Exception): pass
class RuntimeConflictError(Exception): pass
