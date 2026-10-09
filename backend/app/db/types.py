"""Custom SQLAlchemy types for MariaDB-specific features."""

from sqlalchemy.types import UserDefinedType


class MariaDBVector(UserDefinedType[bytes]):
    """Represent the MariaDB VECTOR(N) data type.

    The type is intentionally minimal because vector insertion and search
    operations are performed through explicit MariaDB SQL functions.

    Args:
        dimensions: Number of dimensions in the stored vector.
    """

    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        """Initialize a VECTOR type with a fixed dimensionality.

        Args:
            dimensions: Number of floating-point values in the vector.

        Raises:
            ValueError: If dimensions is not positive.
        """
        if dimensions <= 0:
            raise ValueError("Vector dimensions must be greater than zero.")

        self.dimensions = dimensions

    def get_col_spec(self, **_: object) -> str:
        """Return the MariaDB column definition."""
        return f"VECTOR({self.dimensions})"
