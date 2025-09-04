class ServiceException(Exception):
    """Base exception for the service layer."""
    def __init__(self, name: str, message: str):
        self.name = name
        self.message = message
        super().__init__(self.message)

class NotFoundException(ServiceException):
    """Exception raised when a resource is not found."""
    def __init__(self, resource: str, identifier: any):
        name = "NotFoundException"
        message = f"Resource '{resource}' with identifier '{identifier}' not found."
        super().__init__(name, message)

class InvalidDataException(ServiceException):
    """Exception raised for invalid or contradictory data."""
    def __init__(self, message: str):
        name = "InvalidDataException"
        super().__init__(name, message)

class DatabaseException(ServiceException):
    """Exception raised for database operation failures."""
    def __init__(self, message: str):
        name = "DatabaseException"
        super().__init__(name, message)